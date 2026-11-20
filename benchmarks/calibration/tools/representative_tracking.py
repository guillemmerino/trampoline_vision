"""Reprodueix el contrast històric de quatre preparacions sobre 12 clips complets."""

import argparse
from collections import Counter
from contextlib import ExitStack, closing
import csv
from dataclasses import asdict
import gzip
from html import escape
import json
from pathlib import Path
from statistics import mean
import sys
import time

from benchmarks.calibration.engine.common import (
    atomic_json, digest, exclusive_run, inside, read_json, sha256, verify_artifacts, verify_file,
)
from benchmarks.calibration.engine.evaluation import box_values, load_reference
from benchmarks.calibration.engine.run import monitored, runtime
from benchmarks.calibration.engine.paths import EXPERIMENT_ROOT, ITERATION_ROOT

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / 'benchmarks/calibration/config'
PLAN = ITERATION_ROOT / '05-representative-tracking.json'
ANNOTATIONS = ROOT / 'benchmarks/calibration/annotations/expanded-v1/references'
DETECTOR = read_json(EXPERIMENT_ROOT / 'localization-candidates.json')['detectors'][0]
VARIANTS = ('baseline', 'hard12', 'hard8', 'soft12')


def print_event(event, **values):
    print(json.dumps({'event': event, **values}, ensure_ascii=False), flush=True)


def profile(plan):
    from trampoline_vision.tracking.config import TrackerConfig
    spec = plan['tracker']
    source = read_json(ROOT / spec['profile'])
    source['lifecycle'].update(spec['lifecycle'])
    source['parameters'].update(spec['parameters'])
    return TrackerConfig.from_dict(source)


def frozen_cache(cache_root, case, weights):
    root = cache_root / case['case_id'] / DETECTOR['id']
    marker = root / 'completed.json'
    if not marker.is_file():
        return None
    done = read_json(marker)
    verify_artifacts(root, done['artifacts'])
    attempt = inside(root, done['attempt'])
    meta = read_json(attempt / 'detector.json')
    if (meta['video_sha256'] != case['sha256'] or meta['weights_sha256'] != weights['sha256']
            or meta['settings'] != DETECTOR or meta['precision'] != 'float32'
            or meta['frame_count'] != case['video']['frame_count']):
        raise ValueError(f'Detector cache differs from the frozen plan for {case["case_id"]}')
    return attempt / 'boxes.csv'


def resolve(args):
    plan = read_json(PLAN)
    corpus = read_json(CONFIG / 'corpus.json')
    if read_json(args.dataset / 'corpus.json') != corpus:
        raise ValueError('Dataset does not match the versioned corpus')
    if len(plan['cases']) != 12 or tuple(plan['variants']) != VARIANTS:
        raise ValueError('Plan does not match the expected 12 clips and four variants')
    cases = {c['case_id']: c for c in corpus['cases']}
    weights = next(m for m in corpus['models'] if m['model_id'] == DETECTOR['model'])
    verify_file(inside(args.dataset, weights['path']), weights['sha256'])
    inputs = {}
    for spec in plan['cases']:
        case = cases[spec['id']]
        if spec['panel'] not in ('left', 'right') or case['case_id'] in inputs:
            raise ValueError(f'Invalid case specification: {spec}')
        verify_file(inside(args.dataset, case['path']), case['sha256'])
        source_refs = args.extra_references / (case['case_id'] + '.json')
        if not source_refs.is_file():
            source_refs = ANNOTATIONS / source_refs.name
        if source_refs.is_file():
            refs = load_reference(source_refs, case, allow_provisional=True)
            reference_document = read_json(source_refs) if refs else None
        else:
            refs, reference_document = None, None
        if spec['partition'] == 'previous' and not refs:
            raise ValueError(f'Expected annotations for {case["case_id"]}')
        cache = frozen_cache(args.cache, case, weights)
        inputs[case['case_id']] = dict(case=case, spec=spec, reference=refs, reference_path=source_refs,
                                      ref_document=reference_document, cache=cache)
    return plan, weights, inputs


def serialize_box(box):
    return box_values(asdict(box))


def evidence(box, target):
    shared = max(0., min(box[2], target[2]) - max(box[0], target[0])) * max(0., min(box[3], target[3]) - max(box[1], target[1]))
    box_area = (box[2] - box[0]) * (box[3] - box[1])
    target_area = (target[2] - target[0]) * (target[3] - target[1])
    return {'box': box, 'coverage': shared / target_area, 'area_ratio': box_area / target_area,
            'iou': shared / (box_area + target_area - shared)}


def compare(boxes, target):
    rows = [evidence(box, target) for box in boxes]
    best = max(rows, key=lambda x: (x['coverage'], -x['area_ratio']), default=None)
    best_iou = max(rows, key=lambda x: x['iou'], default=None)
    return {'best_coverage': best, 'best_iou': best_iou,
            'covers90': bool(best and best['coverage'] >= .90),
            'covers90_bounded4': any(r['coverage'] >= .90 and r['area_ratio'] <= 4 for r in rows),
            'iou50': bool(best_iou and best_iou['iou'] >= .50)}


def compare_tracks(tracks, target):
    rows = [dict(evidence(t['bbox'], target), track_id=t['track_id'], evidence=t['evidence'])
            for t in tracks if t['bbox'] is not None and t['state'] != 'finished']
    return sorted(rows, key=lambda t: (-t['iou'], t['track_id']))


def assess(reference, raw, prepared, stages, candidates, track_rows):
    """Use only provisional geometry here; record exact source of metric loss."""
    row = {'reference': reference, 'variants': {}, 'discrepancies': []}
    target = reference['bbox_xyxy']
    if not target:
        row['unscored'] = 'reference_exclusion'
        return row
    row['raw'] = compare(raw, target)
    row['regional'] = compare(prepared, target)
    stage_matches = {k: compare([g['bbox'] for g in groups], target) for k, groups in stages.items()}
    row['stages'] = stage_matches
    for name in VARIANTS:
        active = compare(candidates[name], target)
        matches = compare_tracks(track_rows[name], target)
        observed = [x for x in matches if x['evidence'] == 'observed']
        predicted = [x for x in matches if x['evidence'] == 'predicted']
        ranks = [i for i, box in enumerate(candidates[name], 1)
                 if evidence(box, target)['coverage'] >= .90]
        ranking = stages.get('guard_soft' if name == 'soft12' else 'guard_hard', [])
        before_cut = next((i for i, group in enumerate(ranking, 1)
                           if evidence(group['bbox'], target)['coverage'] >= .90), None)
        row['variants'][name] = dict(candidates=active, observed=observed, predicted=predicted,
                                     first_coverage_rank=ranks[0] if ranks else None,
                                     first_coverage_rank_before_cut=before_cut if name != 'baseline' else None)
        reasons = []
        if not active['covers90']:
            if not row['raw']['covers90'] and not row['regional']['covers90']:
                reasons.append('no_compatible_raw_or_regional_box')
            elif name == 'baseline':
                reasons.append('baseline_grouping')
            elif not row['regional']['covers90']:
                reasons.append('regional_grouping')
            elif name.startswith('hard') and not stage_matches['zone_hard']['covers90']:
                reasons.append('hard_zone')
            elif not stage_matches['guard_soft' if name == 'soft12' else 'guard_hard']['covers90']:
                reasons.append('containment')
            else:
                reasons.append('ranking_cut')
        elif not active['covers90_bounded4']:
            reasons.append('only_wide_coverage')
        if not observed or observed[0]['iou'] < .5:
            reasons.append('prediction_only_iou50' if predicted and predicted[0]['iou'] >= .5 else 'no_observed_track_iou50')
        if len([x for x in observed if x['iou'] >= .5]) > 1:
            reasons.append('multiple_observed_tracks_iou50')
        row['discrepancies'].extend({'variant': name, 'reason': reason} for reason in reasons)
    return row


def track_record(result, events):
    rows = []
    for track in result.tracks:
        bbox = serialize_box(track.bbox) if track.bbox is not None else None
        rows.append(dict(track_id=track.track_id, state=track.state, evidence=track.evidence,
                         candidate_id=track.candidate_id, bbox=bbox,
                         last_observed_s=track.last_observed_timestamp_s))
    return rows, [asdict(e) for e in events]


def review_image(image, target, raw_match, shortlist, track_rows, dest, zone):
    """Preserve the real frame and make stage/ID differences reviewable."""
    from PIL import Image, ImageDraw
    w, h = image.shape[1], image.shape[0]
    step = min(1., 360 / w)
    size = (round(w * step), round(h * step))
    pitch = size[1] + 22
    canvas = Image.new('RGB', (size[0] * 3, 2 * pitch), '#151927')
    clean = Image.fromarray(image[:, :, ::-1]).resize(size, Image.Resampling.LANCZOS)
    panels = [('Original', []), ('YOLO: millor cobertura', [raw_match] if raw_match else [])]
    panels.extend((name, shortlist[name]) for name in VARIANTS)
    for i, (name, boxes) in enumerate(panels):
        x, y = i % 3 * size[0], i // 3 * pitch
        canvas.paste(clean, (x, y + 22))
        draw = ImageDraw.Draw(canvas)
        draw.text((x+5, y+4), name, fill='white')

        def rect(box, color):
            x0, y0, x1, y1 = box
            draw.rectangle((x+x0*step, y+22+y0*step, x+x1*step, y+22+y1*step), outline=color, width=2)

        if name in ('hard8', 'hard12', 'soft12'):
            rect(zone, '#eeeeee')
        for box in boxes:
            rect(box, '#31d9f2')
        if target:
            rect(target, '#ffdf22')
        if target or name != 'baseline':
            for track in track_rows.get(name, ()):
                box = track['bbox']
                if box is None or track['state'] == 'finished':
                    continue
                if target and evidence(box, target)['iou'] < .25:
                    continue
                color = '#75ff62' if track['evidence'] == 'observed' else '#ff7fed'
                x0, y0, _, _ = box
                rect(box, color)
                draw.text((x+x0*step, y+22+y0*step), track['track_id'], fill=color, stroke_width=1, stroke_fill='black')
    canvas.save(dest, quality=88)


def prepare_manifest(case, video, csv_path, output):
    from trampoline_vision.ingestion.manifest import load_manifest
    manifest = {'schema_version': '1.0', 'path_base': 'manifest_directory', 'case_id': case['case_id'],
                'video': {'path': str(video.path), 'expected': case['video']},
                'detections': {'primary': {'path': str(csv_path), 'format': 'person_boxes_csv',
                                           'frame_index_base': 0, 'coordinate_space': 'original_frame_pixels',
                                           'frame_coverage': 'complete_video', 'variant': DETECTOR['id']}}}
    path = output / 'case.json'
    atomic_json(path, manifest)
    return load_manifest(path)


def video_background(video):
    import numpy as np
    from trampoline_vision.ingestion.video_frames import VideoFrameReader
    from benchmarks.calibration.engine.representative import downsample
    # Match the exploratory policy: one frozen 21-image median per clip.
    indices = np.linspace(0, video.frame_count - 1, 21, dtype=int).tolist()
    with closing(VideoFrameReader(video)) as reader:
        images = [downsample(reader.get(i).to_ndarray(format='bgr24')) for i in indices]
    return np.median(np.stack(images), axis=0).astype('uint8'), indices


def evaluate_clip(item, weights, tracker, root, args):
    from trampoline_vision.ingestion.video import probe_video
    from trampoline_vision.ingestion.video_frames import VideoFrameReader
    from trampoline_vision.ingestion.detections import iter_recorded_frames
    from trampoline_vision.preparation.config import PreparationConfig
    from trampoline_vision.tracking.session import TrackingSession
    from benchmarks.calibration.engine.detector import detect
    from benchmarks.calibration.engine.representative import regional_groups, replay_zone, shortlist, tracker_frame
    import numpy as np

    case = item['case']
    case_id = case['case_id']
    video = probe_video(inside(args.dataset, case['path']), case_id)
    expected = case['video']
    if ((video.width_px, video.height_px, video.frame_count)
            != (expected['width_px'], expected['height_px'], expected['frame_count'])
            or abs(video.duration_s - expected['duration_s']) > .01):
        raise ValueError(f'Video metadata differs from the corpus: {case_id}')
    cache_hit = item['cache'] is not None
    if cache_hit:
        csv_path = item['cache']
        detector = {'cache_hit': True, 'source': str(csv_path), 'csv_sha256': sha256(csv_path)}
    else:
        csv_path = root / 'boxes.csv'
        with monitored(args.device) as measures:
            result = detect(video, DETECTOR, inside(args.dataset, weights['path']), csv_path, args.device,
                            progress=lambda done, total: print_event('detect', case=case_id, frames=done, total=total))
        detector = {'cache_hit': False, 'csv_sha256': sha256(csv_path), 'resources': measures, 'result': result}
    atomic_json(root / 'detector.json', detector)
    manifest = prepare_manifest(case, video, csv_path, root)
    start = time.perf_counter()
    background, indices = video_background(video)
    background_s = time.perf_counter() - start
    zone = replay_zone(video, item['spec']['panel'])
    sessions = {name: TrackingSession(tracker, video.fps or 1 / video.frame_durations_s[0]) for name in VARIANTS}
    policy = PreparationConfig.from_dict(read_json(ROOT/'configs/preparation/box-candidates.json')).box_preparation
    refs = item['reference'] or {}
    unlabelled = set(np.linspace(0,video.frame_count - 1,24,dtype=int).tolist()) if not refs else set()
    counters = {n: Counter() for n in VARIANTS}
    ids = {n: Counter() for n in VARIANTS}
    last = {}
    assessments = []
    stage_time = Counter()
    image_dir = root / 'review'
    image_dir.mkdir()
    if item['ref_document']:
        atomic_json(root / 'references.json', item['ref_document'])
    with monitored(args.device) as resources, ExitStack() as stack:
        video_reader = stack.enter_context(closing(VideoFrameReader(video)))
        source_frames = stack.enter_context(closing(iter_recorded_frames(manifest, video, missing_frames_policy='error')))
        trace = stack.enter_context(gzip.open(root/'frames.jsonl.gz','xt',compresslevel=3,encoding='utf-8'))
        for source in source_frames:
            index = source.context.frame_index
            image = video_reader.get(index).to_ndarray(format='bgr24')
            mark = time.perf_counter()
            baseline, groups = regional_groups(source, policy)
            kept, stages = shortlist(groups,image,background,zone)
            prepared = {'baseline': baseline, **{n: tracker_frame(baseline,g) for n,g in kept.items()}}
            stage_time['prepare_all_s'] += time.perf_counter()-mark
            tracks, events, active, provenance = {}, {}, {}, {}
            for name in VARIANTS:
                frame = prepared[name]
                mark = time.perf_counter()
                current = sessions[name].update(frame)
                stage_time[f'tracking_{name}_s'] += time.perf_counter()-mark
                tracks[name], events[name] = track_record(current,sessions[name].events)
                counters[name].update(candidates=len(frame.candidates),
                                      observations=sum(t['evidence']=='observed' for t in tracks[name]),
                                      predictions=sum(t['evidence']=='predicted' and t['state']!='finished' and t['bbox'] is not None
                                                      for t in tracks[name]))
                active[name] = [serialize_box(c.measurement.bbox) for c in frame.candidates]
                if name != 'baseline':
                    provenance[name] = [{'id': c.candidate_id, 'source_detection_ids': c.source_detection_ids,
                                          'score': c.measurement.score, 'score_method': c.measurement.score_method,
                                          'geometry_origin': g['region_origin'], 'bbox': g['bbox']}
                                         for c,g in zip(frame.candidates, kept[name], strict=True)]
            trace.write(json.dumps(dict(frame_index=index,timestamp_s=source.context.timestamp_s,
                                        counts={n:len(b) for n,b in active.items()}, baseline_boxes=active['baseline'],
                                        shortlists=provenance,tracks=tracks,events=events),separators=(',',':'),allow_nan=False)+'\n')
            if index in refs:
                raw = [serialize_box(d.bbox) for d in source.detections]
                record = assess(refs[index],raw,[g['bbox'] for g in groups],stages,active,tracks)
                frame_ref = refs[index]['bbox_xyxy']
                if frame_ref:
                    for name in VARIANTS:
                        match = record['variants'][name]
                        counts = counters[name]
                        viable = [t for t in match['observed'] if t['iou'] >= .5]
                        counts.update(reference_visible=1, coverage90=match['candidates']['covers90'],
                                      coverage90_bounded4=match['candidates']['covers90_bounded4'],
                                      candidates_iou50=match['candidates']['iou50'], observed_iou50=bool(viable))
                        ids[name].update(t['track_id'] for t in viable)
                        if viable:
                            track_id = viable[0]['track_id']
                            if name in last and last[name][1] != track_id:
                                counts['id_changes_between_annotated_matches'] += 1
                                record['discrepancies'].append({'variant':name,'reason':'id_change_between_annotated_matches',
                                                                'previous_frame':last[name][0],'previous_id':last[name][1],
                                                                'current_id':track_id})
                            last[name] = (index,track_id)
                if record['discrepancies']:
                    image_path = f'review/{index:06d}.jpg'
                    best = (record.get('raw', {}).get('best_coverage') or {}).get('box')
                    review_image(image,frame_ref,best,active,tracks,root/image_path,zone)
                    record['image'] = image_path
                record.update(frame_index=index,timestamp_s=source.context.timestamp_s)
                assessments.append(record)
            elif index in unlabelled:
                image_path = f'review/{index:06d}.jpg'
                review_image(image,None,None,active,tracks,root/image_path,zone)
                import cv2
                original = f'review/{index:06d}-original.png'
                if not cv2.imwrite(str(root/original), image):
                    raise OSError(f'Cannot write review frame {original}')
                assessments.append(dict(frame_index=index,timestamp_s=source.context.timestamp_s,image=image_path,
                                        original_image=original, unscored='no_reference',discrepancies=[]))
            if (index+1)%200==0 or index+1==video.frame_count:
                print_event('track',case=case_id,frames=index+1,total=video.frame_count)
        if index+1 != video.frame_count:
            raise ValueError(f'Incomplete replay for {case_id}')
    for name in VARIANTS:
        counters[name]['best_fixed_id_observations'] = max(ids[name].values(),default=0)
    atomic_json(root/'assessment.json',assessments)
    report = {'case':case_id, 'partition':item['spec']['partition'], 'frames':video.frame_count,
              'reference_samples':len(refs), 'reference_status':item['ref_document']['status'] if refs else 'unannotated',
              'human_reviewed':item['ref_document'].get('human_reviewed') if refs else None,
              'background_indices':indices,'zone':zone.tolist(),'background_s':background_s,
              'counts':counters,'timings':stage_time,'resources':resources,'detector_cache_hit':cache_hit}
    atomic_json(root/'completed.json',report)
    return report


def export_review(output, finished, planned):
    """Rebuild durable CSV and HTML from completed clips after each checkpoint."""
    summaries = []
    discrepancies = []
    galleries = []
    for attempt, report in finished:
        case = report['case']
        assessment = read_json(attempt/'assessment.json')
        by_variant = Counter((d['variant'],d['reason']) for r in assessment for d in r['discrepancies'])
        for name in VARIANTS:
            counts = report['counts'][name]
            summaries.append(dict(case=case, partition=report['partition'], variant=name, frames=report['frames'],
                                  reference_status=report['reference_status'], reference_samples=report['reference_samples'],
                                  visible_samples=counts.get('reference_visible'),
                                  candidates_mean=counts['candidates']/report['frames'],
                                  coverage90=counts.get('coverage90'), coverage90_bounded4=counts.get('coverage90_bounded4'),
                                  candidates_iou50=counts.get('candidates_iou50'), observed_iou50=counts.get('observed_iou50'),
                                  id_changes_between_annotated_matches=counts.get('id_changes_between_annotated_matches',0)
                                  if counts.get('reference_visible') else None,
                                  best_fixed_id_observations=counts['best_fixed_id_observations']
                                  if counts.get('reference_visible') else None,
                                  observations=counts['observations'], predictions=counts['predictions'],
                                  discrepancy_count=sum(v for (variant,_),v in by_variant.items() if variant==name),
                                  association_s=report['timings'][f'tracking_{name}_s'],
                                  prepare_all_variants_s=report['timings']['prepare_all_s'],
                                  clip_pass_s=report['resources']['elapsed_s'],
                                  clip_peak_rss_bytes=report['resources']['peak_rss_bytes'],
                                  clip_peak_cuda_allocated_bytes=report['resources'].get('peak_cuda_allocated_bytes'),
                                  detector_cache_hit=report['detector_cache_hit']))
        for row in assessment:
            image = (attempt/row['image']).relative_to(output).as_posix() if 'image' in row else None
            for item in row['discrepancies']:
                active = row['variants'][item['variant']]['candidates']
                discrepancies.append(dict(case=case, partition=report['partition'], frame_index=row['frame_index'],
                                          timestamp_s=row['timestamp_s'], reference_status=report['reference_status'],
                                          variant=item['variant'], reason=item['reason'],
                                          reference_bbox=row['reference']['bbox_xyxy'],
                                          best_coverage=(active['best_coverage'] or {}).get('coverage'),
                                          best_box=(active['best_coverage'] or {}).get('box'),
                                          first_coverage_rank_before_cut=row['variants'][item['variant']]['first_coverage_rank_before_cut'],
                                          assessment=(attempt/'assessment.json').relative_to(output).as_posix(),
                                          image=image, detail=json.dumps(item,ensure_ascii=False)))
            if image:
                labels = ', '.join(f'{x["variant"]}: {x["reason"]}' for x in row['discrepancies'])
                original = ((attempt/row['original_image']).relative_to(output).as_posix()
                            if 'original_image' in row else None)
                galleries.append((case,row['frame_index'],row['timestamp_s'],image,original,
                                  labels or 'Pendent d’anotar'))

    def save_csv(name, rows, keys):
        temp = output/(name+'.tmp')
        with temp.open('w', newline='',encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=keys)
            writer.writeheader()
            writer.writerows(rows)
        temp.replace(output/name)
    if summaries:
        save_csv('summary.csv',summaries,list(summaries[0]))
    fields = ('case','partition','frame_index','timestamp_s','reference_status','variant','reason',
              'reference_bbox','best_coverage','best_box','first_coverage_rank_before_cut','assessment','image','detail')
    save_csv('discrepancies.csv',discrepancies,fields)
    target = output/'review.html'
    sections = []
    for case,index,timestamp,image,original,labels in galleries:
        original_link = (f'<p><a href="{escape(original,quote=True)}">Fotograma original per anotar</a></p>' if original else '')
        sections.append(f'<article><h2>{escape(case)} · #{index} · {timestamp:.2f} s</h2>'
                        f'<p>{escape(labels)}</p><a href="{escape(image,quote=True)}">'
                        f'<img loading="lazy" src="{escape(image,quote=True)}" alt="Comparació de caixes"></a>{original_link}</article>')
    text = f'''<!doctype html><html lang="ca"><meta charset="utf-8"><title>Revisió de tracking</title>
<style>body{{color:#edf1f7;background:#161c28;font:16px system-ui;max-width:1200px;margin:24px auto;padding:0 16px}}
a{{color:#73dce8}} article{{margin:2em 0}} h2{{font-size:1em}} img{{display:block;max-width:100%;height:auto}}</style>
<h1>Discrepàncies i fotogrames pendents d’anotar</h1>
<p>{len(finished)}/{planned} clips complets. Les referències d’IA són provisionals.
Groc · referència. Cian · candidata. Verd · track observat. Magenta · predicció. Blanc · zona.</p>
<p><a href="summary.csv">Resum per clip i variant</a> · <a href="discrepancies.csv">Registre de discrepàncies</a></p>
{''.join(sections)}</html>'''
    temp = target.with_suffix('.tmp')
    temp.write_text(text,encoding='utf-8')
    temp.replace(target)
    atomic_json(output/'status.json',dict(status='complete' if len(finished)==planned else 'incomplete',
                                          planned_clips=planned, completed_clips=len(finished),
                                          discrepancy_rows=len(discrepancies), review_frames=len(galleries)))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--results',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--extra-references',type=Path,default=Path('/extra-references'))
    parser.add_argument('--cache',type=Path)
    parser.add_argument('--device',default='cuda:0')
    parser.add_argument('--threads',type=int,default=8)
    parser.add_argument('--dry-run',action='store_true',help='Verifica inputs i CUDA i mostra el pla.')
    parser.add_argument('--resume',action='store_true',help='Reutilitza els clips complets amb hashes verificats.')
    args = parser.parse_args(argv)
    args.dataset = args.dataset.resolve()
    args.cache = args.cache or args.results/'expanded-localization-v1/run/detections'
    output = (args.output or args.results/'representative-tracking-v1').resolve()
    if not output.is_relative_to(args.results.resolve()) or output == args.results.resolve():
        parser.error('--output must be a child of --results')
    try:
        plan, weights, inputs = resolve(args)
        tracker = profile(plan)
        environment = runtime(args.device,args.threads,[tracker.backend])
        identity = dict(plan=plan, detector=DETECTOR, weights=weights, tracker=asdict(tracker),
                        device=args.device, threads=args.threads, environment=environment,
                        sources={name:{'video':v['case']['sha256'],
                                       'detector_csv':sha256(v['cache']) if v['cache'] else None,
                                       'annotations':sha256(v['reference_path']) if v['reference'] else None}
                                 for name,v in inputs.items()},
                        code={str(p.relative_to(ROOT)):sha256(p) for p in
                              [Path(__file__),ROOT/'benchmarks/calibration/engine/representative.py',
                               ROOT/'configs/preparation/box-candidates.json',
                               *sorted((ROOT/'src/trampoline_vision').rglob('*.py'))]})
        signature = digest(identity)
        print_event('plan',case_ids=list(inputs),frames=sum(v['case']['video']['frame_count'] for v in inputs.values()),
                    jobs=len(inputs)*len(VARIANTS),variants=list(VARIANTS),
                    detector_cache_hits=sum(v['cache'] is not None for v in inputs.values()),
                    clips_with_references=sum(bool(v['reference']) for v in inputs.values()),
                    gpu=environment['gpu'],output=str(output))
        if args.dry_run:
            return 0
        from benchmarks.calibration.engine.common import artifacts
        from benchmarks.calibration.engine.run import attempt_directory, completed
        output.mkdir(parents=True,exist_ok=args.resume)
        with exclusive_run(output/'.lock'):
            run_manifest = output/'run.json'
            if run_manifest.exists():
                if read_json(run_manifest)['signature'] != signature:
                    raise ValueError('The inputs, benchmark code, or runtime changed; choose a new --output')
            else:
                if any(p.name != '.lock' for p in output.iterdir()):
                    raise ValueError('Output already contains files without a study manifest; choose a new --output')
                atomic_json(run_manifest,dict(signature=signature,identity=identity))
            finished = []
            export_review(output, finished, len(inputs))
            for name,item in inputs.items():
                clip = output/'clips'/name
                done = completed(clip,signature)
                if done:
                    attempt = inside(clip,done['attempt'])
                    report = done['report']
                    print_event('resume_clip',case=name)
                else:
                    attempt = attempt_directory(clip)
                    print_event('start_clip',case=name,attempt=attempt.name)
                    report = evaluate_clip(item,weights,tracker,attempt,args)
                    hashes = artifacts(clip,[p for p in attempt.rglob('*') if p.is_file()])
                    atomic_json(clip/'completed.json',dict(signature=signature,attempt=attempt.name,
                                                          report=report,artifacts=hashes))
                finished.append((attempt,report))
                export_review(output,finished,len(inputs))
                print_event('complete_clip',case=name)
            print_event('complete',review=str(output/'review.html'),discrepancies=str(output/'discrepancies.csv'))
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'{type(exc).__name__}: {exc}',file=sys.stderr)
        return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
