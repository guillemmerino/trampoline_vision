"""Executa simulacions controlades i replay de candidates, amb traces auditables."""

import argparse
from collections import Counter, defaultdict
from contextlib import closing, nullcontext
import gzip
import json
import math
from pathlib import Path
import platform
import time
from types import SimpleNamespace

import numpy as np
import scipy

from benchmarks.calibration.engine.common import atomic_json, artifacts, inside, read_json, sha256, verify_artifacts
from benchmarks.calibration.tools.analyze_identity import compatible, endpoint_continuity, minimum_changes
from benchmarks.calibration.tools.trampoline_tracker_prototype import Candidate, Prototype
from trampoline_vision.contracts.geometry import BoundingBox
from trampoline_vision.contracts.observations import FrameContext
from trampoline_vision.contracts.tracking import BoxMeasurement
from trampoline_vision.infrastructure.embedding_cache import ReadOnlyEmbeddingCache

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT/'benchmarks/calibration/config/studies/trampoline-tracker-prototype-v1.json'


def simulated_clip(scenario, seed, config):
    """Genera caixes, descriptors i etiquetes independents de les decisions del tracker."""
    rng = np.random.default_rng(seed)
    period = rng.uniform(.60,.95)
    amplitude = rng.uniform(135,235)
    drift = rng.uniform(20,95)
    start = rng.uniform(445,565)
    clean_appearance = np.eye(8)[:6]
    contact = scenario in ('near_contact','combined','camera_shift')
    shape = scenario in ('box_changes','combined','camera_shift')
    weak = scenario in ('weak_and_missing','combined','camera_shift')
    fps = config['fps']
    frames, labels = [], []
    for index in range(config['frames']):
        timestamp = index/fps
        phase = (timestamp/period+.24)%1
        shift = 65 if scenario=='camera_shift' and index>=config['frames']//2 else 0
        x = start+drift*math.sin(timestamp*1.25)+shift
        y = 730-amplitude*4*phase*(1-phase)
        near_bed = phase<.12 or phase>.88
        entities = []
        if not (weak and near_bed and index%7 in (0,1)):
            width,height = (44,103) if not shape else (34+70*math.sin(phase*math.pi)**4,
                                                       57+54*math.cos(phase*math.pi)**2)
            if shape and index%13 in (4,5):
                y += 24
                height *= .46
            score = rng.uniform(.0012,.018) if weak and (near_bed or index%17 in (10,11)) else rng.uniform(.18,.85)
            entities.append(('gymnast',0,x,y,width,height,score))
        if contact:
            helper_x = start+32*math.sin(timestamp*1.25+.4)+22+shift
            helper_y = 751-13*math.sin(timestamp*2.4)
            entities.append(('assistant',1,helper_x,helper_y,56,92,rng.uniform(.25,.9)))
            if near_bed and index%4 in (0,1):
                entities = [e for e in entities if e[0]!='gymnast']
                entities.append(('mixed',1,(helper_x+x)/2,(helper_y+y)/2,100,125,.45))
        else:
            entities.append(('assistant',1,start+105+shift,751,56,92,.65))
        entities.extend(('other',i,200+i*153+shift,541+(i%2)*55,40,63,.77)
                        for i in (2,3,4))
        if shape and index%4==0:
            entities.append(('other',5,x+rng.uniform(-100,100),y+38,75,49,.026))
        rng.shuffle(entities)
        candidates, truth = [], {}
        for ordinal,(role,person,cx,cy,width,height,score) in enumerate(entities):
            cx,cy = np.array([cx,cy])+rng.normal(0,3 if shape else 1.5,2)
            vector = clean_appearance[person]+rng.normal(0,.15 if shape else .06,8)
            if role=='mixed' or (contact and near_bed and role=='gymnast'):
                vector += .75*clean_appearance[1]
            key = f'{index}:{ordinal}'
            candidates.append(Candidate(key,(cx-width/2,cy-height/2,cx+width/2,cy+height/2),
                                        score,vector/np.linalg.norm(vector)))
            truth[key] = role
        frames.append((timestamp,candidates))
        labels.append(truth)
    return frames,labels


def replay(frames, plan, variant, tracker_type=Prototype):
    """Calcula assignacions amb causalitat excepte a la variant amb retard declarat."""
    tracker = tracker_type(plan,variant)
    lookahead = variant.get('lookahead_frames',0)
    return [tracker.step(timestamp,candidates,frames[index+1:index+1+lookahead])
            for index,(timestamp,candidates) in enumerate(frames)]


def simulation_metrics(labels, assignments):
    """Mesura cobertura, continuïtat i contaminació amb les identitats sintètiques conegudes."""
    count = Counter()
    last_roles, gymnast_ids = {}, set()
    samples = []
    for index,(truth,observed) in enumerate(zip(labels,assignments,strict=True)):
        ids = {identity for key,identity in observed.items() if truth[key]=='gymnast'}
        available = 'gymnast' in truth.values()
        count['gymnast_observed'] += bool(ids)
        count['gymnast_candidate'] += available
        for key,identity in observed.items():
            role = truth[key]
            if role in ('assistant','other') and last_roles.get(identity)=='gymnast':
                count['transfer_events'] += 1
            if identity in gymnast_ids and role in ('assistant','other','mixed'):
                count['contaminated_observations'] += 1
                if role=='mixed':
                    count['mixed_observations'] += 1
            if role!='mixed':
                last_roles[identity] = role
        gymnast_ids.update(ids)
        samples.append((index,ids))
    metrics,_ = endpoint_continuity(samples)
    count.update({key:metrics[key] for key in ('pairs','same_id','changed_id','both_endpoints_observed')})
    count['minimum_changes'] = minimum_changes([ids for _,ids in samples])
    return count


def boxes_from_run(folder, run, expected_video):
    """Llegeix candidates verificades i descriptors desats que coincideixen exactament."""
    appearance = read_json(folder/'botsort-reid.json')['appearance']
    cache_path = run/'appearance-cache'/Path(appearance['cache_path']).name
    with closing(ReadOnlyEmbeddingCache(cache_path,{'video_id':folder.name,'video_sha256':expected_video},
                                       appearance['fingerprint'])) as cache:
        frames, baseline, baseline_reid = [], [], []
        with (folder/'botsort.frames.jsonl').open() as geometry_stream, \
             (folder/'botsort-reid.frames.jsonl').open() as appearance_stream:
            for index,(row,reid_row) in enumerate(zip(map(json.loads,geometry_stream),
                                                      map(json.loads,appearance_stream),strict=True)):
                context = FrameContext(**row['context'])
                if context.frame_index!=index or reid_row['context']!=row['context']:
                    raise ValueError('Ordre de les traces inconsistent')
                measurements = []
                for item in row['candidates']:
                    measurement = dict(item['measurement'])
                    measurement['bbox'] = BoundingBox(**measurement['bbox'])
                    measurements.append(SimpleNamespace(candidate_id=item['candidate_id'],
                                                         measurement=BoxMeasurement(**measurement)))
                source = SimpleNamespace(context=context,source_status=row['source_status'])
                stored = cache.get(SimpleNamespace(source=source,candidates=measurements))
                if stored is None:
                    raise ValueError(f'Falten descriptors del frame {index}')
                candidates = []
                for item,embedding in zip(measurements,stored.embeddings,strict=True):
                    box = item.measurement.bbox
                    candidates.append(Candidate(item.candidate_id,(box.x_min,box.y_min,box.x_max,box.y_max),
                                                item.measurement.score,np.array(embedding.values)))
                frames.append((context.timestamp_s,candidates))
                for trace,destination in ((row,baseline),(reid_row,baseline_reid)):
                    destination.append(({t['candidate_id']:t['track_id'] for t in trace['tracks']
                                         if t['evidence']=='observed' and t['state']!='finished'},
                                        [t['track_id'] for t in trace['tracks'] if t['state']=='lost'],{}))
    return frames,{'botsort_saved':baseline,'botsort_reid_saved':baseline_reid},cache_path


def real_metrics(refs, frames, assignments, mode):
    """Aplica el criteri acordat de continuïtat dispersa amb el mateix conjunt de referències."""
    samples,available = [],0
    for ref in refs:
        index,target = ref['frame_index'],ref['bbox_xyxy']
        candidates = {c.key for c in frames[index][1] if compatible(c.box,target,mode)}
        available += bool(candidates)
        samples.append((index,{identity for key,identity in assignments[index].items() if key in candidates}))
    stats,pairs = endpoint_continuity(samples)
    stats['available_candidates'] = available
    return stats,pairs


def audit_labels(review, run, case):
    """Recupera àncores manuals d'actor per candidata a partir dels tracks que es van revisar."""
    path = review/'review/tracks.jsonl'
    rows = [r for r in map(json.loads,path.open()) if r['case_id']==case]
    votes = defaultdict(set)
    for name in sorted({r['profile'] for r in rows}):
        selected = {r['frame_index']:r for r in rows if r['profile']==name}
        trace_path = run/case/f'{name}.frames.jsonl'
        if any(r['trace_sha256']!=sha256(trace_path) for r in list(selected.values())[:1]):
            raise ValueError('Les etiquetes visuals corresponen a una traça diferent')
        with trace_path.open() as stream:
            for index,line in enumerate(stream):
                if index not in selected:
                    continue
                r = selected[index]
                actors = {identity:role for field,role in (
                    ('gymnast_observed_ids','gymnast'),('assistant_ids','assistant'),
                    ('audience_ids','audience'),('other_ids','other'))
                    for identity in r[field]}
                for track in json.loads(line)['tracks']:
                    if track['evidence']=='observed' and track['track_id'] in actors:
                        votes[(index,track['candidate_id'])].add(actors[track['track_id']])
    return {key:next(iter(values)) for key,values in votes.items() if len(values)==1}


def anchored_transfers(labels, assignments):
    """Identifica reassignacions visibles a les àncores disperses amb rol explícit."""
    last,examples = {},[]
    gymnast_observed = set()
    for (index,key),role in sorted(labels.items()):
        identity = assignments[index].get(key)
        if identity is None:
            continue
        if role=='gymnast':
            gymnast_observed.add(index)
        before = last.get(identity)
        if before and before[1]=='gymnast' and role!='gymnast':
            examples.append({'id':identity,'last_gymnast_frame':before[0],
                             'other_frame':index,'other_actor':role})
        last[identity] = (index,role)
    return {'gymnast_frames_observed':len(gymnast_observed),
            'gymnast_frames_labelled':len({index for (index,_),role in labels.items() if role=='gymnast'}),
            'actor_candidates_labelled':len(labels),'examples':examples}


def run_study(args):
    """Verifica entrades abans d'avaluar i desa traces, mètriques i hashes del replay."""
    start = time.perf_counter()
    plan = read_json(args.plan)
    use_silhouette = 'silhouette_experiment' in plan
    tracker_type = Prototype
    code_paths = [args.plan,Path(__file__),Path(__file__).with_name('trampoline_tracker_prototype.py'),
                  Path(__file__).with_name('analyze_identity.py')]
    if use_silhouette:
        import cv2
        from benchmarks.calibration.tools.trampoline_silhouette import (
            SilhouettePrototype, add_real_silhouettes, add_simulated_silhouettes,
        )
        cv2.setNumThreads(1)
        tracker_type = SilhouettePrototype
        code_paths.extend([Path(__file__).with_name('trampoline_silhouette.py'),
                           ROOT/'src/trampoline_vision/preparation/foreground.py'])
        corpus_path = args.dataset/'corpus.json'
        corpus = {case['case_id']:case for case in read_json(corpus_path)['cases']}
    verify_artifacts(args.run,read_json(args.run/'completed.json')['artifacts'])
    review_marker = read_json(args.review/'review-completed.json')
    verify_artifacts(args.review,review_marker['artifacts'])
    original = read_json(args.run/'inputs.json')
    if plan['cases']!=[c['id'] for c in original['plan']['cases']]:
        raise ValueError('El pla no coincideix amb el run congelat')
    args.output.mkdir(parents=True)
    simulation,real,inputs = {},{},{'sources':{},'plan':plan,'python':platform.python_version(),
                                    'numpy':np.__version__,'scipy':scipy.__version__,
                                    'source_completed_sha256':sha256(args.run/'completed.json'),
                                    'review_completed_sha256':sha256(args.review/'review-completed.json'),
                                    'code_sha256':{p.name:sha256(p) for p in code_paths}}
    if use_silhouette:
        inputs.update(opencv=cv2.__version__, corpus_sha256=sha256(corpus_path))
    config = plan['simulation']
    variants = plan['variants']
    with gzip.open(args.output/'simulated.jsonl.gz','wt',encoding='utf-8') as sim_stream:
        for scenario in config['scenarios']:
            started = time.perf_counter()
            totals = {name:Counter() for name in variants}
            for seed in range(config['seeds']):
                geometry_scenario = 'combined' if scenario=='foreground_clutter' else scenario
                frames,labels = simulated_clip(geometry_scenario,seed,config)
                if use_silhouette:
                    frames = add_simulated_silhouettes(frames,labels,scenario,seed)
                for name,variant in variants.items():
                    result = replay(frames,plan,variant,tracker_type)
                    metrics = simulation_metrics(labels,[a for a,_,_ in result])
                    totals[name].update(metrics)
                    sim_stream.write(json.dumps({'scenario':scenario,'seed':seed,'variant':name,
                                                 'metrics':metrics})+'\n')
            simulation[scenario] = {name:dict(stats) for name,stats in totals.items()}
            print(f'{scenario}: {time.perf_counter()-started:.1f} s',flush=True)
    silhouette_context = (gzip.open(args.output/'real-silhouette.jsonl.gz','wt',encoding='utf-8')
                          if use_silhouette else nullcontext())
    with silhouette_context as silhouette_stream, \
         gzip.open(args.output/'real-traces.jsonl.gz','wt',encoding='utf-8') as traces, \
         gzip.open(args.output/'real-pairs.jsonl.gz','wt',encoding='utf-8') as pairs_stream:
        for case in plan['cases']:
            video_sha = original['detectors'][case]['video_sha256']
            frames,results,cache = boxes_from_run(args.run/case,args.run,video_sha)
            if len(frames)!=original['detectors'][case]['frame_count'] or any(len(c)>12 for _,c in frames):
                raise ValueError('Cobertura o pressupost de candidates inconsistent')
            ref_path = ROOT/'benchmarks/calibration/annotations/expanded-v1/references'/f'{case}.json'
            document = read_json(ref_path)
            if document['video_sha256']!=video_sha:
                raise ValueError('La referència correspon a un altre vídeo')
            refs = [r for r in document['samples'] if r['state']=='visible']
            labels = audit_labels(args.review,args.run,case)
            inputs['sources'][case] = {'reference_sha256':sha256(ref_path),'cache_sha256':sha256(cache)}
            if use_silhouette:
                report = read_json(args.run/case/'botsort.json')
                background = report['preparation_background']['sample_frame_indices']
                video_path = inside(args.dataset,corpus[case]['path'])
                frames = add_real_silhouettes(frames,video_path,case,video_sha,background,
                                             lambda row: silhouette_stream.write(json.dumps(row)+'\n'))
                inputs['sources'][case].update(video_sha256=video_sha,background_indices=background)
            times = {}
            for name,variant in variants.items():
                tick = time.perf_counter()
                results[name] = replay(frames,plan,variant,tracker_type)
                times[name] = time.perf_counter()-tick
            real[case] = {}
            for name,result in results.items():
                observed = [a for a,_,_ in result]
                decisions,modes = Counter(),{}
                for index,(a,p,d) in enumerate(result):
                    decisions.update(d)
                    traces.write(json.dumps({'case_id':case,'variant':name,'frame_index':index,
                                             'observed':a,'predicted_ids':p,'decisions':d})+'\n')
                for mode in ('iou50','coverage25_purity50'):
                    modes[mode],pairs = real_metrics(refs,frames,observed,mode)
                    for pair in pairs:
                        pairs_stream.write(json.dumps(dict(pair,case_id=case,variant=name,mode=mode))+'\n')
                real[case][name] = {'metrics':modes,'visual_anchors':anchored_transfers(labels,observed),
                                    'decisions':dict(decisions),'replay_s':times.get(name)}
            print(f'{case}: {len(frames)} fotogrames',flush=True)
    atomic_json(args.output/'inputs.json',inputs)
    atomic_json(args.output/'summary.json',{'simulation':simulation,'real':real,
                                           'elapsed_s':time.perf_counter()-start})
    atomic_json(args.output/'completed.json',{'artifacts':artifacts(args.output,sorted(args.output.iterdir()))})


def main():
    """Exposa l'experiment amb un destí nou i dos inputs congelats."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,default=PLAN)
    parser.add_argument('--dataset',type=Path,default=ROOT/'data/calibration-v1')
    parser.add_argument('--run',type=Path,default=ROOT/'runs/calibration/identity-continuity-v1')
    parser.add_argument('--review',type=Path,default=ROOT/'runs/calibration/identity-continuity-review-v1')
    parser.add_argument('--output',type=Path,required=True)
    run_study(parser.parse_args())


if __name__=='__main__':
    main()
