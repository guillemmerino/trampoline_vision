"""Comparació aparellada de zones sobre deteccions desades, sense YOLO ni tracking."""

import argparse
from collections import Counter, defaultdict
from contextlib import closing
from dataclasses import asdict, replace
import gzip
from html import escape
import json
from pathlib import Path
import resource
import sys
import time

import cv2

from benchmarks.calibration.engine.common import atomic_json, inside, read_json, sha256, verify_file
from benchmarks.calibration.reviews.human import validate_state
from benchmarks.calibration.tools.prepare_boxes import coverage_metrics, source_frame
from benchmarks.calibration.tools.review_representative import _layer
from trampoline_vision.ingestion.video import probe_video
from trampoline_vision.ingestion.video_frames import VideoFrameReader
from trampoline_vision.preparation.config import PreparationConfig
from trampoline_vision.preparation.foreground import sample_indices
from trampoline_vision.preparation.representative import RepresentativeBoxPreparer
from trampoline_vision.results.preparation import preparation_record


ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / 'benchmarks/calibration/config/iterations/06-zone-comparison.json'
VARIANTS = ('previous_hard', 'previous_soft', 'centered_soft')


def previous_zone(panel):
    """Reprodueix les zones antigues normalitzades, incloent els dos clips amb càmera esquerra."""
    if panel not in ('left', 'right'):
        raise ValueError('Historical zone requires an explicit left/right panel')
    left, right = (0., .69) if panel == 'left' else (.30, 1.)
    return (left + .06*(right-left), .25, left + .94*(right-left), .93)


def variants(config, panel):
    """Varia únicament zona i mode; conserva agrupament, llindars i pressupost comuns."""
    if config.representative_boxes is None or config.representative_boxes.max_candidates != 12:
        raise ValueError('Comparison requires a representative profile with a budget of 12')
    if config.representative_boxes.zone_mode != 'soft':
        raise ValueError('The new common profile must use soft mode')
    return {name: replace(config, representative_boxes=replace(config.representative_boxes,
        zone=previous_zone(panel) if name != 'centered_soft' else config.representative_boxes.zone,
        zone_mode='hard' if name == 'previous_hard' else 'soft')) for name in VARIANTS}


def metrics(boxes, target):
    """Mesura geometria contra una referència; no declara si una caixa parcial és útil."""
    result = coverage_metrics(boxes, target)
    best_iou = 0.
    target_area = (target[2]-target[0])*(target[3]-target[1])
    for box in boxes:
        shared = max(0., min(box.x_max,target[2])-max(box.x_min,target[0])) * max(0., min(box.y_max,target[3])-max(box.y_min,target[1]))
        box_area = (box.x_max-box.x_min)*(box.y_max-box.y_min)
        best_iou = max(best_iou, shared/(box_area+target_area-shared))
    return dict(result, covered_at_095=result['max_reference_coverage'] >= .95, best_iou=best_iou, iou50=best_iou >= .5)


def discrepancies(row):
    """Assenyala canvis de cobertura i fallades comunes; són discrepàncies per revisar, no errors confirmats."""
    reasons = []
    for reference in row['targets']:
        comparisons = {name: row['variants'][name]['metrics'][reference] for name in VARIANTS}
        for metric in ('covered_at_090', 'covered_at_095', 'covered_at_090_area4', 'iou50'):
            states = {name: value[metric] for name,value in comparisons.items()}
            if len(set(states.values())) > 1:
                reasons.append(f'{reference}:{metric}:changed')
        if not comparisons['centered_soft']['covered_at_090']:
            reasons.append(f'{reference}:centered_below_090')
            if not row['raw_metrics'][reference]['covered_at_090']:
                reasons.append(f'{reference}:raw_detector_already_below_090')
    return reasons


def targets_for(sample, state, detector):
    """Separa IA provisional, detecció útil validada i referència humana aprovada o corregida."""
    targets = {}
    if sample['reference']['state'] == 'visible':
        targets['ai_reference'] = sample['reference']['bbox_xyxy']
    entry = state['entries'].get(sample['key'], {}) if state else {}
    if entry.get('presence') == 'visible':
        verdict = entry['detectors'].get(detector, {})
        if verdict.get('verdict') in ('sufficient', 'partial'):
            targets['human_useful_detection'] = next(
                box['bbox_xyxy'] for box in sample['variants'][detector]['boxes']
                if box['det_id'] == verdict['candidate_id'])
        ref = entry['reference']
        if ref['verdict'] in ('approved', 'corrected'):
            targets['human_reference'] = ref['bbox_xyxy']
    return targets


def _card(row, image_name, width, height):
    """Mostra píxels reals, referències i les tres llistes de caixes en paral·lel."""
    targets = ''.join(_layer([box], color) for key,box in row['targets'].items()
                      for color in [('#ffe05c' if key == 'ai_reference' else '#ff65e6')])
    panels = []
    for name, spec in row['variants'].items():
        zone = [v*(width if i%2 == 0 else height) for i,v in enumerate(spec['zone'])]
        panels.append(f'<figure><figcaption>{name}</figcaption><svg viewBox="0 0 {width} {height}">'
            f'<image href="{image_name}" width="{width}" height="{height}"/>'
            f'{_layer([zone], "#65bcff")}{_layer(spec["boxes"], "#43ff8a")}{targets}</svg></figure>')
    details = {name: spec['metrics'] for name,spec in row['variants'].items()}
    return f'<article><h2>{escape(row["key"])}</h2><p>{escape(", ".join(row["discrepancies"]))}</p>' \
        + '<div>'+''.join(panels)+'</div><details><summary>Mètriques i raons de revisió</summary><pre>' \
        + escape(json.dumps(details, ensure_ascii=False, indent=2))+'</pre></details></article>'


def _html(title, body):
    """Construeix pàgines locals sense dependències de xarxa."""
    return '<!doctype html><html lang="ca"><meta charset="utf-8">' \
        f'<title>{escape(title)}</title><style>body{{font:16px sans-serif;background:#18202a;color:white;padding:20px}}' \
        'a{color:#8dcaff}article>div{display:flex}figure{margin:6px;width:33%}svg{width:100%}' \
        'pre{white-space:pre-wrap}td,th{padding:8px;border:1px solid #586473}</style>' \
        f'<h1>{escape(title)}</h1><p>Verd: candidates; blau: zona; groc: referència IA provisional; '\
        'magenta: caixa humana validada. La discrepància geomètrica no confirma una pèrdua del gimnasta.</p>'+body+'</html>'


def resolve(args):
    """Verifica inputs i decisions abans de crear sortides; no permet referències provisionals implícites."""
    if not args.allow_provisional_references:
        raise ValueError('Pass --allow-provisional-references to acknowledge the AI annotations')
    if args.output.exists():
        raise ValueError('Choose a new output directory; previous results are never overwritten')
    plan, bundle = read_json(args.plan), read_json(args.bundle)
    config = PreparationConfig.from_dict(read_json(args.config))
    if plan['schema_version'] != '1.0' or tuple(plan['variants']) != VARIANTS or bundle['schema_version'] != '1.0':
        raise ValueError('Unsupported paired zone comparison plan or bundle')
    detector = plan['detector']
    setting = bundle['detectors'][detector]
    if (setting['model'], setting['confidence'], setting['nms_iou']) != ('yolov8m', .001, .7):
        raise ValueError('Comparison requires the verified YOLOv8m 0.001 / NMS 0.7 detections')
    state = validate_state(read_json(args.decisions), bundle) if args.decisions else None
    cases = {c['case_id']:c for c in read_json(args.dataset/'corpus.json')['cases']}
    requested = set(args.case or [c['id'] for c in plan['cases']])
    if requested - {c['id'] for c in plan['cases']}:
        raise ValueError('Requested case does not belong to the comparison plan')
    grouped, seen = defaultdict(list), set()
    for sample in bundle['frames']:
        if sample['case_id'] not in requested:
            continue
        if sample['key'] in seen or sample['key'] != f"{sample['case_id']}:{sample['frame_index']}":
            raise ValueError('Duplicate or inconsistent review frame')
        seen.add(sample['key'])
        case = cases[sample['case_id']]
        if sample['video_sha256'] != case['sha256']:
            raise ValueError('Bundle and corpus video identity differ')
        source_frame(sample, detector, args.bundle, case['video'])
        grouped[sample['case_id']].append(sample)
    inputs = []
    for spec in plan['cases']:
        if spec['id'] not in requested:
            continue
        samples = sorted(grouped[spec['id']], key=lambda x: x['frame_index'])
        if len(samples) != plan['expected_samples_per_case']:
            raise ValueError(f'Unexpected annotation sample count for {spec["id"]}')
        case = cases[spec['id']]
        path = inside(args.dataset, case['path'])
        verify_file(path, case['sha256'])
        inputs.append((spec, case, path, samples, variants(config, spec['panel'])))
    identity = {'plan':plan, 'config':asdict(config), 'detector':setting,
                'bundle_sha256':sha256(args.bundle), 'plan_sha256':sha256(args.plan),
                'config_sha256':sha256(args.config), 'corpus_sha256':sha256(args.dataset/'corpus.json'),
                'decisions_sha256':sha256(args.decisions) if args.decisions else None,
                'videos':{case['case_id']:case['sha256'] for _,case,_,_,_ in inputs},
                'reference_status':'provisional_ai_accepted_for_study_pending_human_validation',
                'code_sha256':{str(path.relative_to(ROOT)):sha256(path) for path in [Path(__file__).resolve(),
                    ROOT/'benchmarks/calibration/tools/prepare_boxes.py',
                    ROOT/'benchmarks/calibration/tools/review_representative.py',
                    *sorted((ROOT/'src/trampoline_vision/preparation').glob('*.py')),
                    ROOT/'src/trampoline_vision/results/preparation.py']}}
    return detector, state, inputs, identity


def run(args):
    """Avalua les variants aparellades, desa auditoria completa i destaca les discrepàncies."""
    started = time.perf_counter()
    detector, state, inputs, identity = resolve(args)
    scope = {'videos':len(inputs), 'annotated_frames':sum(len(item[3]) for item in inputs),
             'variants':list(VARIANTS), 'inference':False, 'tracking':False}
    if args.dry_run:
        print(json.dumps(dict(scope, status='preflight_passed'), indent=2))
        return scope
    args.output.mkdir(parents=True, exist_ok=False)
    atomic_json(args.output/'inputs.json', identity)
    if state:
        atomic_json(args.output/'decisions-snapshot.json', state)
    totals, per_case, pair_counts = {}, {}, Counter()
    links, discrepancy_count = [], 0
    with gzip.open(args.output/'frames.jsonl.gz', 'xt', encoding='utf-8') as stream, \
            (args.output/'discrepancies.jsonl').open('x', encoding='utf-8') as differences:
        for spec, case, path, samples, configs in inputs:
            case_id = case['case_id']
            video = probe_video(path, case_id)
            if (video.frame_count,video.width_px,video.height_px) != (
                    case['video']['frame_count'],case['video']['width_px'],case['video']['height_px']):
                raise ValueError('Decoded video geometry or timeline differs from corpus')
            indices = sample_indices(video.frame_count)
            tick = time.perf_counter()
            with closing(VideoFrameReader(video)) as reader:
                backgrounds = [reader.get(i).to_ndarray(format='bgr24') for i in indices]
            preparers = {name:RepresentativeBoxPreparer(case_id, config, backgrounds) for name,config in configs.items()}
            del backgrounds
            background_s = time.perf_counter()-tick
            folder = args.output/case_id
            folder.mkdir()
            cards, counts = [], {name:Counter() for name in VARIANTS}
            with closing(VideoFrameReader(video)) as reader:
                for sample in samples:
                    image = reader.get(sample['frame_index']).to_ndarray(format='bgr24')
                    source = source_frame(sample, detector, args.bundle, case['video'])
                    targets = targets_for(sample,state,detector)
                    row = {'key':sample['key'], 'partition':sample['partition'], 'reference':sample['reference'],
                           'reference_status':identity['reference_status'], 'targets':targets,
                           'raw_metrics':{ref:metrics([d.bbox for d in source.detections],target) for ref,target in targets.items()},
                           'source':asdict(source), 'variants':{}}
                    for name,preparer in preparers.items():
                        tick = time.perf_counter()
                        result = preparer.prepare_with_audit(source,image)
                        elapsed = time.perf_counter()-tick
                        prepared = preparation_record(result.frame, configs[name], audit=result)
                        boxes = [c.measurement.bbox for c in result.frame.candidates]
                        row['variants'][name] = {'zone':configs[name].representative_boxes.zone,
                            'boxes':[[b.x_min,b.y_min,b.x_max,b.y_max] for b in boxes],
                            'candidates':prepared['candidates'], 'selection_audit':prepared['selection_audit'],
                            'preparation_s':elapsed, 'metrics':{ref:metrics(boxes,target) for ref,target in row['targets'].items()}}
                        count = counts[name]
                        count.update(frames=1, source_boxes=len(source.detections), selected_boxes=len(boxes), preparation_s=elapsed)
                        for ref,values in row['variants'][name]['metrics'].items():
                            count[f'{ref}:n'] += 1
                            for metric in ('covered_at_090','covered_at_095','covered_at_090_area4','iou50'):
                                count[f'{ref}:{metric}'] += int(values[metric])
                    for ref in row['targets']:
                        for before,after in (('previous_hard','previous_soft'),('previous_soft','centered_soft'),('previous_hard','centered_soft')):
                            for metric in ('covered_at_090','covered_at_095','covered_at_090_area4','iou50'):
                                a,b = (row['variants'][name]['metrics'][ref][metric] for name in (before,after))
                                pair_counts[f'{ref}:{before}_to_{after}:{metric}:n'] += 1
                                pair_counts[f'{ref}:{before}_to_{after}:{metric}:lost'] += int(a and not b)
                                pair_counts[f'{ref}:{before}_to_{after}:{metric}:gained'] += int(b and not a)
                    row['discrepancies'] = discrepancies(row)
                    stream.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
                    if row['discrepancies']:
                        name = f'frame-{sample["frame_index"]:06d}.jpg'
                        if not cv2.imwrite(str(folder/name),image):
                            raise OSError('Could not save discrepancy frame')
                        row['image'] = f'{case_id}/{name}'
                        differences.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
                        cards.append(_card(row,name,video.width_px,video.height_px))
                        discrepancy_count += 1
            (folder/'index.html').write_text(_html(case_id, ''.join(cards) or '<p>Cap discrepància geomètrica detectada.</p>'), encoding='utf-8')
            per_case[case_id] = {'partition':samples[0]['partition'], 'panel':spec['panel'],
                'background_indices':indices,'background_s':background_s,'variants':{name:dict(c) for name,c in counts.items()}}
            for name,count in counts.items():
                for group in ('all',samples[0]['partition']):
                    totals.setdefault(group, {}).setdefault(name, Counter()).update(count)
            links.append(f'<li><a href="{case_id}/index.html">{case_id}</a>: {len(cards)} fotogrames per revisar</li>')
            print(json.dumps({'case':case_id,'frames':len(samples),'discrepancies':len(cards)},ensure_ascii=False),flush=True)
    summary = {'schema_version':'1.0','scope':scope,'totals':totals,'per_case':per_case,'paired_changes':dict(pair_counts),
        'discrepancy_frames':discrepancy_count,'elapsed_s':time.perf_counter()-started,
        'peak_process_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        'timing_scope':'Preflight, video decoding, shared background, 3 preparations, metrics, JSONL and JPG/HTML export; no MP4.',
        'limitations':['Sparse AI annotations remain provisional and are not exhaustive human ground truth.',
            'Geometry thresholds 90%, 95%, IoU 0.5 and area 4x are diagnostics; partial useful boxes require visual review.',
            'Human useful detection measures preservation of an approved YOLO box, not an independent full-body reference.',
            'Same competition capture; development and reserved strata reported separately, no generalization claim.',
            'Only annotated frames are prepared; full clips are decoded to fit backgrounds and reach samples.',
            'No inference, temporal identities, prediction or skeleton evaluated.']}
    atomic_json(args.output/'summary.json',summary)
    table = '<table><tr><th>Variant</th><th>IA ≥90%</th><th>IA ≥90% i àrea≤4×</th><th>Caixa humana útil ≥95%</th></tr>'
    for name,count in totals['all'].items():
        table += f'<tr><td>{name}</td><td>{count["ai_reference:covered_at_090"]}/{count["ai_reference:n"]}</td>' \
            f'<td>{count["ai_reference:covered_at_090_area4"]}/{count["ai_reference:n"]}</td>' \
            f'<td>{count["human_useful_detection:covered_at_095"]}/{count["human_useful_detection:n"]}</td></tr>'
    (args.output/'index.html').write_text(_html('Comparació de zones sense tracking',table+'</table><ul>'+''.join(links)+'</ul>'),encoding='utf-8')
    (args.output/'ASSESSMENT.md').write_text('# Comparació aparellada de zones\n\n'
        f'{scope["videos"]} vídeos, {scope["annotated_frames"]} fotogrames anotats i tres variants. '
        f'{discrepancy_count} fotogrames amb discrepàncies per revisar a `index.html`.\n\n'
        'Els denominadors, els guanys i pèrdues aparellats i els resultats per vídeo i partició són a `summary.json`. '
        '`frames.jsonl.gz` conserva originals, seleccions i auditories; `discrepancies.jsonl`, els casos de revisió. '
        'Les anotacions d’IA continuen provisionals. Els canvis geomètrics no són errors confirmats.\n\n'
        f'Total: {summary["elapsed_s"]:.2f} s, incloent lectura, preparació i exportació JPG/HTML; sense MP4 ni GPU. '
        f'RSS màxim del procés: {summary["peak_process_rss_bytes"]/2**20:.1f} MiB, incloent el bundle carregat.\n',encoding='utf-8')
    atomic_json(args.output/'completed.json',{'summary_sha256':sha256(args.output/'summary.json'),
        'inputs_sha256':sha256(args.output/'inputs.json'),'frames_sha256':sha256(args.output/'frames.jsonl.gz')})
    return summary


def main(argv=None):
    """Exposa preflight i execució amb destinació nova i reconeixement explícit de referències IA."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--decisions',type=Path)
    parser.add_argument('--config',type=Path,default=ROOT/'configs/preparation/representative-boxes.json')
    parser.add_argument('--plan',type=Path,default=PLAN)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--allow-provisional-references',action='store_true')
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--case',action='append')
    args = parser.parse_args(argv)
    try:
        run(args)
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print(f'Zone comparison failed: {exc}',file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
