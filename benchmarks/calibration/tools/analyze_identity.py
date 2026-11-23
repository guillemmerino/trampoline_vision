"""Revisa traces congelades i genera diagnòstics dispersos, sense cap tracker.

La geometria serveix per seleccionar exemples; no produeix anotacions
d'identitat ni converteix referències IA disperses en validació contínua.
"""

import argparse
from collections import Counter
import json
from pathlib import Path

from benchmarks.calibration.engine.common import atomic_json, inside, read_json, sha256, verify_artifacts, verify_file
from benchmarks.calibration.tools.identity_comparison import PROFILES, compare_candidates

ROOT = Path(__file__).resolve().parents[3]


def geometry(box, reference):
    """Retorna IoU, cobertura de referència i puresa de candidata, sense decidir identitat."""
    if isinstance(box, dict):
        box = [box[k] for k in ('x_min', 'y_min', 'x_max', 'y_max')]
    shared = max(0, min(box[2],reference[2])-max(box[0],reference[0])) * max(0,min(box[3],reference[3])-max(box[1],reference[1]))
    area = (box[2]-box[0])*(box[3]-box[1])
    target = (reference[2]-reference[0])*(reference[3]-reference[1])
    return {'iou': shared/(area+target-shared), 'coverage': shared/target, 'purity': shared/area}


def compatible(box, reference, mode):
    """Aplica dos diagnòstics explícits; cap llindar equival a caixa útil validada."""
    value = geometry(box, reference)
    return value['iou'] >= .5 if mode == 'iou50' else value['coverage'] >= .25 and value['purity'] >= .5


def minimum_changes(sets):
    """Calcula el límit inferior de canvis entre conjunts de matches dispersos."""
    costs = {}
    for ids in sets:
        if ids:
            costs = {identity: min((cost+(old != identity) for old,cost in costs.items()), default=0)
                     for identity in ids}
    return min(costs.values(), default=0)


def endpoint_continuity(samples):
    """Compara IDs als extrems d'anotacions visibles consecutives d'un sol actor.

    Un ID compartit acredita continuïtat entre extrems segons el criteri
    d'estudi, sense afirmar què succeeix als frames intermedis. Els buits
    queden al denominador total i no se salten per buscar un match posterior.
    Amb duplicats, cada parell pot tenir un ID compartit diferent; la
    intersecció global comprova separadament si existeix un únic ID comú.
    """
    samples = sorted(samples, key=lambda item: item[0])
    if len({frame for frame,_ in samples}) != len(samples):
        raise ValueError('Duplicate annotation frame')
    pairs = []
    counts = Counter(same_id=0, changed_id=0, missing_left=0, missing_right=0, missing_both=0)
    for (first,left),(last,right) in zip(samples,samples[1:]):
        shared = left & right
        status = ('missing_both' if not left and not right else 'missing_left' if not left else
                  'missing_right' if not right else 'same_id' if shared else 'changed_id')
        counts[status] += 1
        pairs.append({'first_frame':first,'last_frame':last,'span_frames':last-first,
                      'left_ids':sorted(left),'right_ids':sorted(right),'shared_ids':sorted(shared),'status':status})
    matched = [ids for _,ids in samples if ids]
    common = set.intersection(*matched) if matched else set()
    paired = counts['same_id']+counts['changed_id']
    occurrences = Counter(identity for _,ids in samples for identity in ids)
    best_count = max(occurrences.values(),default=0)
    return {'pairs':len(pairs),**counts,'both_endpoints_observed':paired,
            'same_id_fraction_when_both_observed':counts['same_id']/paired if paired else None,
            'same_id_fraction_all_visible_pairs':counts['same_id']/len(pairs) if pairs else None,
            'visible_annotations':len(samples),'matched_annotations':len(matched),
            'single_id_covers_all_matched_annotations':bool(common),
            'single_id_covers_all_visible_annotations':bool(common) and len(matched)==len(samples),
            'best_fixed_id_annotation_count':best_count,
            'best_fixed_ids':sorted(identity for identity,count in occurrences.items() if count==best_count)}, pairs


def analyze(run, dataset, output):
    """Verifica l'execució i publica només diagnòstics nous en una carpeta exclusiva."""
    if output.exists():
        raise ValueError('Choose a new review destination')
    done = read_json(run/'completed.json')
    verify_artifacts(run, done['artifacts'])
    identity = read_json(run/'inputs.json')
    code_changes = [name for name,checksum in identity['code_sha256'].items()
                    if not (ROOT/name).exists() or sha256(ROOT/name) != checksum]
    results, samples, pairs = [], [], []
    for spec in identity['plan']['cases']:
        case = spec['id']
        folder = run/case
        count = read_json(folder/'botsort.json')['totals']['frames']
        compare_candidates(folder, count)
        reference_path = ROOT/'benchmarks/calibration/annotations/expanded-v1/references'/f'{case}.json'
        reference = read_json(reference_path)
        if reference['video_sha256'] != identity['detectors'][case]['video_sha256']:
            raise ValueError('Reference video mismatch')
        corpus = read_json(dataset/'corpus.json')
        video = next(c for c in corpus['cases'] if c['case_id'] == case)
        verify_file(inside(dataset,video['path']), reference['video_sha256'])
        references = {s['frame_index']:s for s in reference['samples']}
        frame_records = {name: {} for name in PROFILES}
        per_profile = {}
        for name in PROFILES:
            report = read_json(folder/f'{name}.json')
            events, tracks = Counter(), set()
            with (folder/f'{name}.frames.jsonl').open() as stream:
                for index,line in enumerate(stream):
                    frame = json.loads(line)
                    if frame['context']['frame_index'] != index:
                        raise ValueError('Nonconsecutive trace')
                    events.update(e['kind'] for e in frame['events'])
                    tracks.update(t['track_id'] for t in frame['tracks'])
                    if index in references:
                        frame_records[name][index] = frame
            if index+1 != count:
                raise ValueError('Frame count mismatch')
            per_profile[name] = {'all_actors': {'track_ids':len(tracks),'events':dict(events), **report['totals']},
                                 'elapsed_s':report['elapsed_s'], 'appearance':report.get('appearance')}
        modes = {}
        for mode in ('iou50','coverage25_purity50'):
            counts = {name:Counter() for name in PROFILES}
            sets = {name:[] for name in PROFILES}
            unique = {name:set() for name in PROFILES}
            availability = 0
            for index, ref in sorted(references.items()):
                target = ref['bbox_xyxy']
                if ref['state'] != 'visible' or target is None:
                    continue
                candidates = frame_records['ocsort'][index]['candidates']
                accepted = {c['candidate_id'] for c in candidates if compatible(c['measurement']['bbox'],target,mode)}
                availability += bool(accepted)
                row = {'case_id':case,'subject_id':f'{case}:gymnast','frame_index':index,'reference':ref,'mode':mode,
                       'candidate_ids':sorted(accepted),'profiles':{}}
                for name in PROFILES:
                    frame = frame_records[name][index]
                    observed = [t for t in frame['tracks'] if t['evidence']=='observed' and t['candidate_id'] in accepted and t['state']!='finished']
                    predicted = [t for t in frame['tracks'] if t['evidence']=='predicted' and t['bbox'] and t['state']!='finished' and compatible(t['bbox'],target,mode)]
                    ids = {t['track_id'] for t in observed}
                    counts[name].update(observed_matches=bool(ids), prediction_matches=bool(predicted),
                                        prediction_only=bool(predicted) and not ids,
                                        available_no_observation=bool(accepted) and not ids)
                    sets[name].append((index,ids))
                    unique[name].update(ids)
                    row['profiles'][name] = {'observed_ids':sorted(ids),'predicted_ids':[t['track_id'] for t in predicted],
                        'unassigned_candidates':{c['candidate_id']:c.get('unassigned_reason') for c in frame['candidates'] if c['candidate_id'] in accepted and c.get('unassigned_reason')}}
                samples.append(row)
            continuity = {}
            for name in PROFILES:
                continuity[name], details = endpoint_continuity(sets[name])
                pairs.extend(dict(pair,case_id=case,subject_id=f'{case}:gymnast',mode=mode,profile=name)
                             for pair in details)
            modes[mode] = {'visible_references':sum(s['state']=='visible' for s in references.values()),
                           'available_candidates':availability,
                           'profiles':{n:{**counts[n], 'distinct_matched_ids':len(unique[n]),
                                          'minimum_changes_across_sparse_matches':minimum_changes([ids for _,ids in sets[n]]),
                                          'endpoint_continuity':continuity[n]} for n in PROFILES}}
        results.append({'case_id':case,'frames':count,'reference_sha256':sha256(reference_path),
                        'reference_samples':len(references),'reference_states':dict(Counter(s['state'] for s in references.values())),
                        'diagnostics':modes,'profiles':per_profile})
    output.mkdir(parents=True)
    result = {'run_completed_sha256':sha256(run/'completed.json'),'run_inputs_sha256':sha256(run/'inputs.json'),
              'reviewer':'agent:Codex','human_validated':False,
              'integrity':{'verified_artifacts':len(done['artifacts']),'candidate_parity':True,'changed_source_files':code_changes},
              'scope':'sparse_provisional_geometry_not_identity_validation','cases':results}
    atomic_json(output/'diagnostics.json',result)
    with (output/'samples.jsonl').open('x') as stream:
        for row in samples:
            stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    with (output/'pairs.jsonl').open('x') as stream:
        for row in pairs:
            stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    return result


def sheets(run, dataset, output, case, indices, *, prefix='overview', references=True):
    """Dibuixa píxels originals, candidates i matches geomètrics per inspecció provisional."""
    import cv2
    from PIL import Image, ImageDraw, ImageFont
    output.mkdir(parents=True,exist_ok=True)
    refs = read_json(ROOT/'benchmarks/calibration/annotations/expanded-v1/references'/f'{case}.json')
    refs = {s['frame_index']:s.get('bbox_xyxy') for s in refs['samples']} if references else {}
    wanted = set(indices)
    traces = {}
    for name in PROFILES:
        with (run/case/f'{name}.frames.jsonl').open() as stream:
            traces[name] = {i:json.loads(line) for i,line in enumerate(stream) if i in wanted}
    capture = cv2.VideoCapture(str(dataset/'videos'/f'{case}.mp4'))
    font = ImageFont.load_default(size=15)
    small = ImageFont.load_default(size=11)
    tiles = []
    for index in indices:
        capture.set(cv2.CAP_PROP_POS_FRAMES,index)
        ok,image = capture.read()
        if not ok:
            raise ValueError('Missing frame')
        tile = Image.new('RGB',(384,556),'#101820')
        tile.paste(Image.fromarray(image[:,:,::-1]).resize((384,432)),(0,24))
        draw = ImageDraw.Draw(tile)
        draw.text((4,3),f'{case[4:]}  #{index}',font=font,fill='white')
        target = refs.get(index)
        for c in traces['ocsort'][index]['candidates']:
            b=c['measurement']['bbox']
            xy=(b['x_min']*.4,b['y_min']*.4+24,b['x_max']*.4,b['y_max']*.4+24)
            useful=target and compatible(b,target,'coverage25_purity50')
            draw.rectangle(xy,outline='#ff5f5f' if useful else '#55b887',width=2 if useful else 1)
            draw.text(xy[:2],c['candidate_id'].split(':')[-1],font=font,fill='white',stroke_width=1,stroke_fill='black')
        if target:
            draw.rectangle((target[0]*.4,target[1]*.4+24,target[2]*.4,target[3]*.4+24),outline='#ffe050',width=2)
        for ordinal,name in enumerate(PROFILES):
            ids=[]
            if references and target:
                for t in traces[name][index]['tracks']:
                    if t['bbox'] and t['state']!='finished' and compatible(t['bbox'],target,'coverage25_purity50'):
                        ids.append(t['track_id'].split(':')[-1]+('p' if t['evidence']=='predicted' else 'o'))
            elif not references:
                ids=[t['candidate_id'].split(':')[-1]+'>'+t['track_id'].split(':')[-1]
                     for t in traces[name][index]['tracks'] if t['evidence']=='observed' and t['state']!='finished']
            caption = f'{name}: {",".join(ids) or ("-" if target or not references else "sense referencia")}'
            draw.text((4,456+ordinal*24),caption,font=small,fill='white')
        tiles.append(tile)
    capture.release()
    paths=[]
    for start in range(0,len(tiles),16):
        group=tiles[start:start+16]
        canvas=Image.new('RGB',(1536,556*((len(group)+3)//4)),'#101820')
        for i,tile in enumerate(group):
            canvas.paste(tile,((i%4)*384,(i//4)*556))
        path=output/f'{prefix}-{start//16:02d}.jpg'
        canvas.save(path,quality=90)
        paths.append(str(path))
    return paths


def main(argv=None):
    """Exposa diagnòstics complets o làmines de frames explícits, sense reexecutar models."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,default=ROOT/'runs/calibration/identity-continuity-v1')
    parser.add_argument('--dataset',type=Path,default=ROOT/'data/calibration-v1')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--case')
    parser.add_argument('--frames',nargs='+',type=int)
    parser.add_argument('--prefix',default='overview')
    parser.add_argument('--without-reference',action='store_true')
    args=parser.parse_args(argv)
    if args.case:
        print(json.dumps(sheets(args.run,args.dataset,args.output,args.case,args.frames,prefix=args.prefix,
                                references=not args.without_reference)))
    else:
        result=analyze(args.run,args.dataset,args.output)
        print(json.dumps({'integrity':result['integrity'],'cases':[{k:c[k] for k in ('case_id','reference_states','diagnostics')} for c in result['cases']]},indent=2))


if __name__=='__main__':
    main()
