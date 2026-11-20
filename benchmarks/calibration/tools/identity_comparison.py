"""Orquestra quatre perfils amb deteccions congelades i revisió temporal separada.

El preflight no prepara fotogrames ni instancia trackers. L'execució explícita
consumeix els casos d'ús de producció; no importa detector ni recovery.
"""

import argparse
from contextlib import closing
from dataclasses import asdict
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import time
from types import SimpleNamespace

from benchmarks.calibration.engine.common import (
    atomic_json, artifacts, inside, read_json, sha256, verify_artifacts, verify_file,
)

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / 'benchmarks/calibration/config/studies/identity-continuity-v1.json'
PROFILES = ('ocsort', 'bytetrack', 'botsort', 'botsort-reid')


def environment():
    """Verifica el runtime fixat, sense carregar pesos ni executar associacions."""
    expected = {'torch': '2.7.1', 'torchvision': '0.22.1', 'trackers': '2.6.1',
                'boxmot': '16.0.9', 'psutil': '7.0.0'}
    for name, version in expected.items():
        if metadata.version(name).split('+')[0] != version:
            raise ValueError(f'Expected {name}=={version}')
    for name in ('ffprobe', 'ffmpeg'):
        if not shutil.which(name):
            raise ValueError(f'Missing {name}')
    import av
    import cv2
    import torch
    import torchvision
    import trackers
    from boxmot import BotSort
    torch.set_num_threads(4)
    cv2.setNumThreads(1)
    return {'python': platform.python_version(), 'platform': platform.platform(),
            'image_id': os.environ.get('CALIBRATION_IMAGE_ID'),
            'device': 'cpu', 'threads': 4, 'cpu_limit': 4, 'memory_limit_bytes': 8 * 1024**3,
            'packages': dict(sorted((d.metadata['Name'], d.version) for d in metadata.distributions()
                                    if d.metadata['Name'])),
            'ffmpeg': subprocess.check_output(['ffmpeg', '-version'], text=True).splitlines()[0]}


def resolve(args):
    """Comprova hashes, metadades, CSV complets i configuracions abans de crear cap run."""
    from trampoline_vision.ingestion.manifest import load_manifest
    from trampoline_vision.ingestion.video import probe_video
    from trampoline_vision.ingestion.detections import iter_recorded_frames
    from trampoline_vision.preparation.config import PreparationConfig
    from trampoline_vision.tracking.config import TrackerConfig

    if args.output.exists():
        raise ValueError('Choose a new output; no overwrite or resume')
    plan = read_json(PLAN)
    if read_json(args.dataset/'corpus.json') != read_json(ROOT/'benchmarks/calibration/config/corpus.json'):
        raise ValueError('Dataset differs from versioned corpus')
    corpus = read_json(args.dataset/'corpus.json')
    cases = {c['case_id']: c for c in corpus['cases']}
    prep_path = ROOT/plan['preparation']['path']
    verify_file(prep_path, plan['preparation']['sha256'])
    preparation = PreparationConfig.from_dict(read_json(prep_path))
    model = next(m for m in corpus['models'] if m['model_id'] == 'osnet')
    weights = inside(args.dataset, model['path'])
    verify_file(weights, model['sha256'])
    profiles = {}
    for name in PROFILES:
        spec = plan['profiles'][name]
        path = ROOT/spec['path']
        verify_file(path, spec['sha256'])
        value = read_json(path)
        if value['appearance']:
            value['appearance'] = {'provider': 'osnet', 'weights': str(weights), 'sha256': model['sha256'],
                                   'device': 'cpu', 'threads': 4,
                                   'cache_dir': str(args.output/'appearance-cache')}
        profiles[name] = TrackerConfig.from_dict(value)
    resolved = []
    for spec in plan['cases']:
        case = cases[spec['id']]
        video_path = inside(args.dataset, case['path'])
        verify_file(video_path, case['sha256'])
        cache_root = inside(args.cache, f"{spec['id']}/{plan['detector']['id']}")
        marker = read_json(cache_root/'completed.json')
        verify_artifacts(cache_root, marker['artifacts'])
        attempt = inside(cache_root, marker['attempt'])
        csv_path = attempt/'boxes.csv'
        verify_file(csv_path, spec['csv_sha256'])
        meta = read_json(attempt/'detector.json')
        if (meta['settings'] != plan['detector'] or meta['video_sha256'] != case['sha256']
                or meta['weights_sha256'] != plan['detector_weights_sha256']
                or meta['precision'] != 'float32' or meta['frame_count'] != case['video']['frame_count']):
            raise ValueError('Frozen detector metadata differs')
        video = probe_video(video_path, case['case_id'])
        expected = case['video']
        actual = {k: getattr(video, k) for k in expected}
        if actual != expected or any(abs(dt-1/30) > .0001 for dt in video.frame_durations_s):
            raise ValueError('Video timeline or geometry differs')
        manifest_data = {'schema_version': '1.0', 'path_base': 'manifest_directory', 'case_id': case['case_id'],
                         'video': {'path': str(video_path), 'expected': expected},
                         'detections': {'primary': {'path': str(csv_path), 'format': 'person_boxes_csv',
                             'frame_index_base': 0, 'coordinate_space': 'original_frame_pixels',
                             'frame_coverage': 'complete_video', 'variant': plan['detector']['id']}}}
        # El manifest temporal valida tot el CSV sense crear cap sortida d'estudi.
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'case.json'
            atomic_json(path, manifest_data)
            manifest = load_manifest(path)
            with closing(iter_recorded_frames(manifest, video, missing_frames_policy='error')) as frames:
                count = sum(1 for _ in frames)
            if count != video.frame_count:
                raise ValueError('Incomplete frame sequence')
        resolved.append((case, video, manifest_data, meta))
    code = {str(p.relative_to(ROOT)): sha256(p) for folder in ('src/trampoline_vision', 'benchmarks/calibration/tools')
            for p in sorted((ROOT/folder).rglob('*.py'))}
    code.update({str(p.relative_to(ROOT)): sha256(p) for p in (
        ROOT/'benchmarks/calibration/commands/run-identity-comparison.sh',
        ROOT/'benchmarks/calibration/engine/common.py',
        ROOT/'benchmarks/calibration/config/studies/identity-continuity-v1.md')})
    identity = {'plan': plan, 'plan_sha256': sha256(PLAN), 'code_sha256': code,
                'corpus_sha256': sha256(args.dataset/'corpus.json'),
                'preparation': asdict(preparation), 'profiles': {n: asdict(c) for n,c in profiles.items()},
                'detectors': {c['case_id']: m for c,_,_,m in resolved},
                'recovery': 'not_invoked', 'identity_validation': 'pending_continuous_review'}
    return preparation, profiles, resolved, identity


def audit_video(manifest, video, preparation, folder):
    """Desa originals, selecció completa i vídeo de candidates amb IDs locals visibles."""
    from PIL import Image, ImageDraw
    from trampoline_vision.ingestion.detections import iter_recorded_frames
    from trampoline_vision.ingestion.video_frames import VideoFrameReader
    from trampoline_vision.preparation.foreground import sample_indices
    from trampoline_vision.preparation.representative import RepresentativeBoxPreparer
    from trampoline_vision.results.preparation import preparation_record
    from trampoline_vision.results.overlay import RenderStyle, HEADER_HEIGHT, output_dimensions
    from trampoline_vision.results.video import encode_visualization
    from trampoline_vision.ingestion.video import probe_video
    from trampoline_vision.application.visualization import validate_rendered_video

    style = RenderStyle(view='all', min_confidence=0, min_visible_points=1)
    with closing(VideoFrameReader(video)) as reader:
        preparer = RepresentativeBoxPreparer(video.video_id, preparation,
            (reader.get(i).to_ndarray(format='bgr24') for i in sample_indices(video.frame_count)))
    decoded_frame = None

    def supply(index, decoded):
        """Rep els mateixos píxels que dibuixa el codificador."""
        nonlocal decoded_frame
        decoded_frame = (index, decoded)

    def render(image, annotated, style):
        """Dibuixa totes les candidates sense suggerir quina és el gimnasta."""
        canvas = Image.new('RGB', output_dimensions(image.width, image.height, style), '#101820')
        canvas.paste(image, (0, HEADER_HEIGHT))
        draw = ImageDraw.Draw(canvas)
        draw.text((8, 8), f'Candidates | frame {annotated.context.frame_index}', fill='white')
        for candidate in annotated.frame.candidates:
            box = candidate.measurement.bbox
            xy = (box.x_min, box.y_min+HEADER_HEIGHT, box.x_max, box.y_max+HEADER_HEIGHT)
            draw.rectangle(xy, outline='#43ff8a', width=2)
            draw.text(xy[:2], candidate.candidate_id, fill='white', stroke_width=1, stroke_fill='black')
        return canvas, {'preparation': {'candidates': len(annotated.frame.candidates)}}

    with (folder/'preparation.jsonl').open('x', encoding='utf-8') as stream:
        def frames():
            """Prepara i serialitza cada instant conservant fonts i exclusions."""
            with closing(iter_recorded_frames(manifest, video, missing_frames_policy='error')) as source:
                for raw in source:
                    if decoded_frame[0] != raw.context.frame_index:
                        raise ValueError('Decoded frame misalignment')
                    audit = preparer.prepare_with_audit(raw, decoded_frame[1].to_ndarray(format='bgr24'))
                    stream.write(json.dumps(preparation_record(audit.frame, preparation, audit=audit),
                                            ensure_ascii=False, allow_nan=False)+'\n')
                    yield SimpleNamespace(frame=audit.frame, context=raw.context,
                                          source_status=raw.source_status, detections=raw.detections)
        encode_visualization(video, frames(), folder/'candidates.mp4', style, 0, video.frame_count,
                             renderer=render, decoded_callback=supply)
    rendered = probe_video(folder/'candidates.mp4', video.video_id)
    return validate_rendered_video(video, rendered, 0, video.frame_count, style)


def compare_candidates(folder, frame_count):
    """Exigeix candidates idèntiques als quatre perfils i a l'auditoria completa."""
    from contextlib import ExitStack
    with ExitStack() as stack:
        audit = stack.enter_context((folder/'preparation.jsonl').open())
        streams = [stack.enter_context((folder/f'{name}.frames.jsonl').open()) for name in PROFILES]
        for index in range(frame_count):
            expected = json.loads(next(audit))
            for stream in streams:
                row = json.loads(next(stream))
                candidates = [{k:v for k,v in c.items() if k not in ('provenance', 'unassigned_reason')}
                              for c in row['candidates']]
                if row['context']['frame_index'] != index or candidates != expected['candidates']:
                    raise ValueError('Tracker input differs from shared preparation')
        if next(audit, None) is not None or any(next(s, None) is not None for s in streams):
            raise ValueError('Extra frames')


def main(argv=None):
    """Comprova per defecte; --execute autoritza explícitament les dotze execucions."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=Path('/data'))
    parser.add_argument('--cache', type=Path, default=Path('/results/expanded-localization-v1/run/detections'))
    parser.add_argument('--output', type=Path, default=Path('/results/identity-continuity-v1'))
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args(argv)
    started = time.perf_counter()
    preparation, profiles, cases, identity = resolve(args)
    identity['environment'] = environment()
    scope = {'status': 'preflight_passed', 'videos': len(cases), 'profiles': list(PROFILES),
             'source_frames': sum(v.frame_count for _,v,_,_ in cases), 'tracking_runs': 12,
             'detector_inference': False, 'tracking_executed': False, 'recovery': False,
             'plan_sha256': identity['plan_sha256'], 'environment': identity['environment'],
             'preflight_elapsed_s': time.perf_counter()-started}
    if not args.execute:
        print(json.dumps(scope, ensure_ascii=False, indent=2))
        return 0
    from trampoline_vision.application.tracking import track_case
    from trampoline_vision.ingestion.manifest import load_manifest
    import psutil
    process = psutil.Process()
    args.output.mkdir(parents=True, exist_ok=False)
    atomic_json(args.output/'inputs.json', identity)
    summaries = []
    for case, video, manifest_data, _ in cases:
        folder = args.output/case['case_id']
        folder.mkdir()
        atomic_json(folder/'case.json', manifest_data)
        manifest = load_manifest(folder/'case.json')
        tick, cpu = time.perf_counter(), process.cpu_times()
        candidate_validation = audit_video(manifest, video, preparation, folder)
        for name, tracker in profiles.items():
            print(json.dumps({'event': 'tracking_start', 'case': case['case_id'], 'profile': name}), flush=True)
            track_case(manifest, video, folder/f'{name}.json', folder/f'{name}.frames.jsonl',
                       preparation=preparation, tracker=tracker, video_output=folder/f'{name}.mp4',
                       missing_frames_policy='error')
        compare_candidates(folder, video.frame_count)
        final_cpu = process.cpu_times()
        summaries.append({'case': case['case_id'], 'frames': video.frame_count,
                          'elapsed_s': time.perf_counter()-tick,
                          'cpu_user_s': final_cpu.user-cpu.user, 'cpu_system_s': final_cpu.system-cpu.system,
                          'candidate_video_validation': candidate_validation})
    import resource
    atomic_json(args.output/'summary.json', {'cases': summaries, 'identity_accuracy': 'not_evaluated',
                'elapsed_s': time.perf_counter()-started, 'peak_process_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
                'resource_scope': 'sequential_process_including_preflight_decode_preparation_reid_encode; excludes_child_ffprobe'})
    atomic_json(args.output/'completed.json', {'artifacts': artifacts(args.output,
                sorted(p for p in args.output.rglob('*') if p.is_file() and 'appearance-cache' not in p.parts))})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
