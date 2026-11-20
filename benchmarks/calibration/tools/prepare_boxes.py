"""Executa i mesura preparation sobre un paquet de deteccions ja enregistrades.

Adaptador experimental del bundle de revisió al contracte de producció. Desa
un JSONL complet per revisar en una altra iteració, amb referències separades
de l'algoritme. No executa detector, tracker, GPU ni lectura de vídeos.
"""

import argparse
from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path
import platform
import resource
import sys
import time

from benchmarks.calibration.engine.common import atomic_json, read_json, sha256
from benchmarks.calibration.engine.paths import CONFIG_ROOT, PROJECT_ROOT
from benchmarks.calibration.reviews.human import validate_state
from trampoline_vision.contracts.geometry import BoundingBox
from trampoline_vision.contracts.observations import DetectionProvenance, FrameContext, FrameDetections, PersonBoxDetection
from trampoline_vision.preparation.config import PreparationConfig
from trampoline_vision.preparation.pipeline import prepare_frame
from trampoline_vision.results.preparation import preparation_record


def source_frame(sample, detector, bundle_path, video):
    """Situa cada caixa en el bundle original, amb coordenades, temps i confiança intactes."""
    context = FrameContext(sample['case_id'], sample['frame_index'], sample['timestamp_s'],
                           1 / video['fps'], sample['width'], sample['height'])
    if ((context.width_px, context.height_px) != (video['width_px'], video['height_px'])
            or not 0 <= context.frame_index < video['frame_count']
            or abs(context.timestamp_s - context.frame_index / video['fps']) > 1e-6):
        raise ValueError('Bundle frame differs from corpus timeline or geometry')
    detections = []
    for ordinal, box in enumerate(sample['variants'][detector]['boxes']):
        index = box['det_id']
        if type(index) is not int or index < 0:
            raise ValueError('Bundle detection requires a non-negative integer ID')
        bbox = BoundingBox(*box['bbox_xyxy'])
        if not 0 <= bbox.x_min < bbox.x_max <= context.width_px or not 0 <= bbox.y_min < bbox.y_max <= context.height_px:
            raise ValueError('Bundle detection lies outside original pixels')
        provenance = DetectionProvenance(str(bundle_path), f"{sample['key']}/variants/{detector}/boxes/{ordinal}",
                                         context.frame_index, index, detector, 'original')
        detections.append(PersonBoxDetection(f'{context.frame_index}:box:{index}', bbox, box['confidence'], provenance))
    return FrameDetections(context, tuple(detections), 'present')


def coverage_metrics(boxes, reference):
    """Diagnòstic de cobertura de la caixa de referència, amb excés d'àrea separat.

    Ni 90% ni el control d'àrea 4× són llindars òptims: són punts de lectura
    explícits. La referència no intervé en l'agrupament ni en el representant.
    """
    ref = BoundingBox(*reference)
    ref_area = (ref.x_max-ref.x_min)*(ref.y_max-ref.y_min)
    coverages, bounded = [], []
    for box in boxes:
        intersection = max(0., min(ref.x_max,box.x_max)-max(ref.x_min,box.x_min)) * max(0., min(ref.y_max,box.y_max)-max(ref.y_min,box.y_min))
        area_ratio = (box.x_max-box.x_min)*(box.y_max-box.y_min)/ref_area
        coverage = intersection/ref_area
        coverages.append(coverage)
        if coverage >= .9:
            bounded.append(area_ratio)
    return {'max_reference_coverage': max(coverages, default=0.),
            'covered_at_090': bool(bounded), 'covered_at_090_area4': any(r<=4 for r in bounded),
            'min_area_ratio_at_090': min(bounded,default=None)}


def _percentile(values, fraction):
    """Percentil interpolat per descriure latència d'un fotograma, no FPS d'inferència."""
    ordered = sorted(values)
    position = (len(ordered)-1)*fraction
    low = int(position)
    return ordered[low] + (ordered[min(low+1,len(ordered)-1)]-ordered[low])*(position-low)


def run(bundle_path, config_path, output, *, corpus_path=CONFIG_ROOT/'corpus.json', detector='yolov8m-conf0001-nms070', decisions_path=None):
    """Publica una execució nova amb JSONL, configuració, hashes, diagnòstic i recursos.

    Rebutja qualsevol carpeta existent. Les decisions humanes es validen contra
    el bundle i només serveixen per avaluar la conservació, mai per preparar.
    """
    started = time.perf_counter()
    bundle_path, config_path, output = Path(bundle_path).resolve(), Path(config_path).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError('Choose a new preparation output directory; existing results are never overwritten')
    bundle = read_json(bundle_path)
    if bundle.get('schema_version') != '1.0' or not bundle.get('frames') or detector not in bundle.get('detectors',{}):
        raise ValueError('Expected review bundle schema 1.0 with frames and requested detector')
    config = PreparationConfig.from_dict(read_json(config_path))
    cases = {c['case_id']:c for c in read_json(corpus_path)['cases']}
    decisions = validate_state(read_json(decisions_path),bundle) if decisions_path else None
    identity = {'bundle_sha256':sha256(bundle_path),'run_signature':bundle['run_signature'],
                'config_sha256':sha256(config_path),'corpus_sha256':sha256(corpus_path),
                'decisions_sha256':sha256(decisions_path) if decisions_path else None,
                'detector':bundle['detectors'][detector]}
    identity['code_sha256'] = {name:sha256(PROJECT_ROOT/name) for name in (
        'src/trampoline_vision/preparation/boxes.py','src/trampoline_vision/preparation/config.py',
        'src/trampoline_vision/preparation/pipeline.py','src/trampoline_vision/contracts/tracking.py',
        'src/trampoline_vision/results/preparation.py','benchmarks/calibration/tools/prepare_boxes.py')}
    counts, latencies, samples, seen = Counter(), [], [], set()
    output.mkdir(parents=True, exist_ok=False)
    atomic_json(output/'inputs.json',identity)
    atomic_json(output/'config.json',{'schema_version':'1.0',**asdict(config)})
    if decisions:
        atomic_json(output/'decisions-snapshot.json',decisions)
    with (output/'frames.jsonl').open('x',encoding='utf-8') as stream:
        for sample in bundle['frames']:
            if sample['key'] in seen or sample['key'] != f"{sample['case_id']}:{sample['frame_index']}":
                raise ValueError('Duplicate or inconsistent bundle frame key')
            seen.add(sample['key'])
            source = source_frame(sample,detector,bundle_path,cases[sample['case_id']]['video'])
            tick = time.perf_counter_ns()
            prepared = prepare_frame(source,config)
            latencies.append((time.perf_counter_ns()-tick)/1e6)
            record = preparation_record(prepared,config)
            # Scientific provenance stays explicit in each standalone sample.
            record['sample'] = {k:sample[k] for k in ('key','partition','video_sha256','reference_sha256')}
            record['reference'] = sample['reference']
            record['reference_status'] = 'provisional_ai_accepted_for_study'
            stream.write(json.dumps(record,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n')
            refs = [ref for c in prepared.candidates for ref in c.source_detection_ids]
            if len(refs)!=len(source.detections) or set(refs)!={d.detection_id for d in source.detections}:
                raise ValueError('Incomplete source preservation')
            counts.update({'frames':1,'source_boxes':len(source.detections),'candidates':len(prepared.candidates),
                           'grouped_alternatives':len(source.detections)-len(prepared.candidates),'relations':len(prepared.relations)})
            row = {'key':sample['key'],'case_id':sample['case_id'],'partition':sample['partition'],
                   'source_boxes':len(source.detections),'candidates':len(prepared.candidates),'relations':len(prepared.relations)}
            if sample['reference']['state']=='visible':
                original = coverage_metrics([d.bbox for d in source.detections],sample['reference']['bbox_xyxy'])
                representative = coverage_metrics([c.measurement.bbox for c in prepared.candidates],sample['reference']['bbox_xyxy'])
                row.update(original=original,prepared=representative)
                counts['visible_ai_samples']+=1
                for name in ('covered_at_090','covered_at_090_area4'):
                    counts['original_'+name]+=original[name];counts['prepared_'+name]+=representative[name]
                    counts['lost_'+name]+=original[name] and not representative[name]
            entry = decisions['entries'].get(sample['key'],{}) if decisions else {}
            verdict = entry.get('detectors',{}).get(detector,{})
            if entry.get('presence')=='visible' and verdict.get('verdict') in ('sufficient','partial'):
                ref = f"{sample['frame_index']}:box:{verdict['candidate_id']}"
                owner = next(c for c in prepared.candidates if ref in c.source_detection_ids)
                chosen = next(d for d in source.detections if d.detection_id==ref)
                target = chosen.bbox
                comparison = coverage_metrics([owner.measurement.bbox],[target.x_min,target.y_min,target.x_max,target.y_max])
                counts['human_useful_samples']+=1
                counts['human_exact_representative']+=owner.source_detection_ids[0]==ref
                counts['human_selected_box_covered090']+=comparison['covered_at_090']
                row['human']={'verdict':verdict['verdict'],'source_detection_id':ref,
                              'representative_detection_id':owner.source_detection_ids[0],**comparison}
            samples.append(row)
    result = {'schema_version':'1.0','task':'prepare_saved_boxes','identity':identity,'counts':dict(counts),'samples':samples,
              'effective_config':{'schema_version':'1.0',**asdict(config)},
              'resources':{'preparation_s':sum(latencies)/1000,'mean_ms_per_frame':sum(latencies)/len(latencies),
                           'p50_ms_per_frame':_percentile(latencies,.5),'p95_ms_per_frame':_percentile(latencies,.95),
                           'max_ms_per_frame':max(latencies),'total_elapsed_s':time.perf_counter()-started,
                           'peak_process_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
                           'platform':platform.platform(),'gpu_used':False,'inference_executed':False,
                           'python_version':sys.version,
                           'timing_note':'Preparation only excludes bundle loading, adaptation, metrics and JSONL export. Total includes these; no video generation.',
                           'memory_note':'Process RSS includes full review bundle loading; not incremental preparation memory.',
                           'cache_note':'Saved detector outputs reused; no model, GPU or embedding cache accessed.'},
              'limitations':['Sparse AI references accepted for study, not exhaustive human ground truth.',
                             '90% reference coverage and area4 are exploratory diagnostics, not validated acceptance thresholds.',
                             'Human selected bbox coverage is not an independent full-body reference.',
                             'No tracking, identity accuracy, actor selection or skeleton reconstruction evaluated.']}
    atomic_json(output/'result.json',result)
    c=result['counts'];r=result['resources']
    text=(f"# Preparació de caixes enregistrades\n\n{c['frames']} fotogrames de {len({s['case_id'] for s in samples})} vídeos; "
          f"{c['source_boxes']} deteccions originals, {c['candidates']} candidats, {c['grouped_alternatives']} alternatives agrupades i {c['relations']} relacions ambigües.\n\n"
          f"Temps de preparació: {r['preparation_s']:.3f} s; mitjana {r['mean_ms_per_frame']:.3f} ms/frame; p95 {r['p95_ms_per_frame']:.3f} ms/frame. "
          f"Total amb lectura, adaptació, diagnòstic i exportació: {r['total_elapsed_s']:.3f} s. Sense generació de vídeo ni ús de GPU. "
          f"RSS màxim del procés: {r['peak_process_rss_bytes']/2**20:.1f} MiB, incloent carregar tot el bundle.\n\n"
          "Totes les caixes, confiances i procedències originals són a `frames.jsonl`, separades dels representants. "
          "La configuració i els hashes es desen amb el resultat. Les referències d’IA originals continuen provisionals i acceptades per a l’estudi.\n\n"
          "El JSON de resultat inclou cobertura de referència, excés d’àrea i conservació humana. "
          "Els llindars 90% i àrea 4× són diagnòstics exploratoris. No s’han executat tracking ni esquelets.\n")
    (output/'ASSESSMENT.md').write_text(text,encoding='utf-8')
    files = [p for p in output.iterdir() if p.is_file()]
    atomic_json(output/'checksums.json',{p.name:sha256(p) for p in files})
    return result


def main(argv=None):
    """Comanda independent, amb inputs explícits i output nou per cada iteració."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--config',type=Path,default=PROJECT_ROOT/'configs/preparation/box-candidates.json')
    parser.add_argument('--corpus',type=Path,default=CONFIG_ROOT/'corpus.json')
    parser.add_argument('--detector',default='yolov8m-conf0001-nms070')
    parser.add_argument('--decisions',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        result=run(args.bundle,args.config,args.output,corpus_path=args.corpus,detector=args.detector,decisions_path=args.decisions)
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print(f'Preparation failed: {exc}',file=sys.stderr)
        return 2
    print(json.dumps({'output':str(args.output),'counts':result['counts'],'resources':result['resources']},indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
