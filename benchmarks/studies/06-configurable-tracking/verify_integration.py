"""Regressió d'integració 0.5 amb les entrades i traces congelades de l'estudi 05.

No avalua precisió ni ajusta llindars. Verifica descriptors reals, replay
normalitzat i el cas d'ús públic, sense executar de nou cap detector o pose.
El cache NPZ antic només s'importa després de verificar inputs, runtime,
pesos, checksum, offsets i vectors contra l'estudi congelat.
"""

import argparse
from dataclasses import asdict, replace
from importlib.metadata import version
import json
from pathlib import Path
import sys

import numpy as np

from trampoline_vision import __version__
from trampoline_vision.application.appearance import AppearanceService
from trampoline_vision.application.tracking import track_case
from trampoline_vision.contracts.appearance import CandidateEmbedding, FrameAppearance
from trampoline_vision.ingestion.manifest import load_manifest
from trampoline_vision.ingestion.recorded_boxes import iter_box_frames
from trampoline_vision.ingestion.video import probe_video
from trampoline_vision.ingestion.video_frames import VideoFrameReader
from trampoline_vision.perception.appearance.config import AppearanceConfig
from trampoline_vision.perception.appearance.osnet import OSNetExtractor, file_sha256
from trampoline_vision.preparation.config import PreparationConfig
from trampoline_vision.preparation.pipeline import prepare_frame
from trampoline_vision.results.tracking import tracking_record
from trampoline_vision.tracking.config import TrackerConfig
from trampoline_vision.tracking.session import TrackingSession


def normalized(record):
    """Compara decisions exactes; només tradueix els prefixes d'IDs canviats deliberadament a 0.5."""
    tracks = []
    for sample in record['tracks']:
        sample = dict(sample)
        sample['track_id'] = sample['track_id'].split(':')[-1]
        if sample['candidate_id']:
            sample['candidate_id'] = sample['candidate_id'].replace(':yolo_candidate:', ':box_candidate:')
        tracks.append(sample)
    events = [{**event, 'track_id': event['track_id'].split(':')[-1]} for event in record['events']]
    return {'context': record['context'], 'source_status': record['source_status'], 'tracks': tracks,
            'events': events, 'unassigned_candidate_ids': [cid.replace(':yolo_candidate:', ':box_candidate:') for cid in record['unassigned_candidate_ids']]}


def main():
    """Escriu evidència nova en un directori exclusiu i retorna error si divergeix qualsevol regressió."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--legacy', type=Path, required=True)
    parser.add_argument('--tfm', type=Path, required=True)
    parser.add_argument('--weights', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    summary = json.loads((args.legacy/'summary.json').read_text())
    protocol = json.loads((args.legacy/'protocol.json').read_text())
    if file_sha256(args.legacy/'protocol.json') != summary['protocol_sha256']:
        raise ValueError('Legacy protocol differs')
    if file_sha256(args.weights) != summary['weights_sha256']:
        raise ValueError('Legacy weights differ')
    for name in ('boxmot', 'trackers', 'torch', 'torchvision', 'numpy', 'opencv-python', 'av'):
        if version(name) != summary['versions'][name]:
            raise ValueError(f'Frozen runtime differs: {name}')
    result = {'software_version': __version__, 'purpose': 'integration_regression_not_accuracy_evaluation', 'cases': {}}
    preparation = PreparationConfig()
    for case_id, previous in summary['cases'].items():
        case_root = args.output/case_id
        case_root.mkdir()
        manifest_path = case_root/'manifest.json'
        manifest_path.write_text(json.dumps(dict(schema_version='1.0', case_id=case_id, path_base='manifest_directory',
            video={'path': str((args.tfm/f'jumping_score/output_clips/{case_id}.mp4').resolve())},
            detections={'primary': dict(format='person_boxes_csv', path=str((args.tfm/f'Tracking_system/output_videos/{case_id}_bboxes.csv').resolve()),
                frame_index_base=0, frame_coverage='complete_video', coordinate_space='original_frame_pixels', variant='study06')})))
        manifest = load_manifest(manifest_path)
        video = probe_video(manifest.video_path, case_id)
        if file_sha256(video.path) != previous['video_sha256'] or file_sha256(manifest.detections_path) != previous['csv_sha256']:
            raise ValueError('Legacy source bytes differ')
        npz = args.legacy/case_id/'embeddings.npz'
        if file_sha256(npz) != previous['embeddings']['cache_sha256']:
            raise ValueError('Legacy descriptor cache differs')
        with np.load(npz, allow_pickle=False) as archive:
            features, offsets = archive['features'], archive['offsets']
        frames = [prepare_frame(frame, preparation) for frame in iter_box_frames(manifest, video)]
        expected = np.r_[0, np.cumsum([len(frame.candidates) for frame in frames])]
        if not np.array_equal(offsets, expected) or features.shape != (int(offsets[-1]), 512) or not np.isfinite(features).all():
            raise ValueError('Legacy cache shape/order differs')
        if not np.allclose(np.linalg.norm(features, axis=1), 1, atol=1e-4):
            raise ValueError('Legacy cache vectors are not normalized')
        model = AppearanceConfig('osnet', str(args.weights.resolve()), summary['weights_sha256'],
                                 cache_dir=str(args.output/'cache'), threads=4)
        service = AppearanceService(model, video, manifest, preparation)
        try:
            # Xarxa i preprocessament reals sobre tres instants separats, sense entrenament.
            reader = VideoFrameReader(video)
            descriptor_errors = {}
            try:
                for index in (0, video.frame_count//2, video.frame_count-1):
                    actual = service.extractor.extract(frames[index], reader.get(index).to_ndarray(format='bgr24'))
                    matrix = np.asarray([e.values for e in actual.embeddings], dtype=np.float32)
                    old = features[offsets[index]:offsets[index+1]]
                    descriptor_errors[str(index)] = float(np.max(np.abs(matrix-old)))
                    if not np.allclose(matrix, old, atol=2e-6, rtol=1e-5):
                        raise ValueError(f'OSNet preprocessing differs at {case_id}:{index}')
            finally:
                reader.close()
            for index, frame in enumerate(frames):
                vectors = FrameAppearance(frame.source.context, service.extractor.fingerprint, tuple(
                    CandidateEmbedding(candidate.candidate_id, tuple(float(v) for v in vector))
                    for candidate, vector in zip(frame.candidates, features[offsets[index]:offsets[index+1]])))
                service.cache.put(frame, vectors)
            variants = {}
            for variant, backend in [('ocsort', 'ocsort'), ('botsort_motion', 'botsort'), ('botsort_reid', 'botsort')]:
                config = TrackerConfig(backend=backend, appearance=model if variant == 'botsort_reid' else None)
                session = TrackingSession(config, video.fps)
                compared, differences = 0, []
                with (args.legacy/case_id/f'{variant}.frames.jsonl').open() as stream:
                    for frame, line in zip(frames, stream):
                        descriptors = service.for_frame(frame) if config.appearance else None
                        tracked = session.update(frame, descriptors)
                        current = tracking_record(tracked, session.events, config)
                        if normalized(current) != normalized(json.loads(line)):
                            differences.append(frame.source.context.frame_index)
                        compared += 1
                    if stream.readline():
                        raise ValueError('Legacy trace has extra frames')
                if compared != video.frame_count:
                    raise ValueError('Legacy trace is incomplete')
                variants[variant] = {'compared_frames': compared, 'different_frames': differences, 'exact': not differences}
                print(case_id, variant, 'differences', len(differences), flush=True)
            # ByteTrack no té una traça anterior: smoke complet i particions verificades pel domini.
            session = TrackingSession(TrackerConfig(backend='bytetrack'), video.fps)
            for frame in frames:
                session.update(frame)
            result['cases'][case_id] = {'descriptor_max_absolute_error': descriptor_errors, 'variants': variants,
                                        'bytetrack_smoke_frames': len(frames)}
        finally:
            service.close()
        if case_id == next(iter(summary['cases'])):
            # Cas d'ús complet: cache importat + informe/JSONL de tot el clip.
            full = track_case(manifest, video, case_root/'reid.json', case_root/'reid.frames.jsonl',
                              tracker=TrackerConfig(backend='botsort', appearance=model))
            result['public_replay'] = {'frames': full['totals']['frames'], 'appearance': full['appearance']}
            # Primera inferència real dins el flux de renderitzat i segon replay només amb cache.
            live_model = replace(model, cache_dir=str(args.output/'live-cache'))
            first = track_case(manifest, video, case_root/'live.json', case_root/'live.frames.jsonl',
                video_output=case_root/'live.mp4', end_s=.1, tracker=TrackerConfig(backend='botsort', appearance=live_model))
            second = track_case(manifest, video, case_root/'cached.json', case_root/'cached.frames.jsonl',
                end_s=.1, tracker=TrackerConfig(backend='botsort', appearance=live_model))
            if first['appearance']['cache_miss_frames'] != 3 or second['appearance']['cache_hit_frames'] != 3 or second['appearance']['model_loaded']:
                raise ValueError('Live inference/cache replay did not follow the expected path')
            result['public_inference'] = {'first_appearance': first['appearance'], 'second_appearance': second['appearance'], 'video_validation': first['validation']}
    result['all_traces_exact'] = all(variant['exact'] for case in result['cases'].values() for variant in case['variants'].values())
    (args.output/'results.json').write_text(json.dumps(result, indent=2) + '\n')
    if not result['all_traces_exact']:
        raise SystemExit('Integration changed frozen tracking decisions; inspect results.json')


if __name__ == '__main__':
    main()
