"""Fixtures amb tracking real de domini i backend controlat, sense dependències visuals."""

from dataclasses import asdict
import json
from pathlib import Path
from types import SimpleNamespace

from helpers_boxes import box_frame
from trampoline_vision.contracts.observations import VideoAsset
from trampoline_vision.contracts.recovery import TrackingTrace
from trampoline_vision.ingestion.recovery import _frame
from trampoline_vision.results.tracking import tracking_record
from trampoline_vision.tracking.backend import BackendUpdate
from trampoline_vision.tracking.config import TrackerConfig
from trampoline_vision.tracking.session import TrackingSession


def records_and_video(root, pattern=None, timestamps=None):
    """Simula confirmació, pèrdua, recuperació, finalització i censura dreta de diversos actors."""
    pattern = pattern if pattern is not None else [
        {0: 'observed', 1: 'observed'}, {0: 'observed', 1: 'observed'},
        {0: 'lost', 1: 'observed'}, {0: 'no_box'}, {0: 'observed'},
        {0: 'observed', 2: 'observed'}, {2: 'lost'}, {2: 'lost'}]
    times = tuple(timestamps) if timestamps else tuple(i/30 for i in range(len(pattern)))
    durations = tuple(b-a for a, b in zip(times, times[1:])) + (1/30,)
    video = VideoAsset('boxes', Path(root)/'video.mp4', 96, 64, 30, times, durations)
    backend = SimpleNamespace(requires_appearance=False)
    config = TrackerConfig(confirmation_frames=1)
    session, boxes, records = TrackingSession(config, 30, backend=backend), {}, []
    for index, states in enumerate(pattern):
        frame = box_frame(index, tuple(tid for tid, state in states.items() if state == 'observed'))
        frame = type(frame)(type(frame.source)(video.frame(index), frame.source.detections, frame.source.source_status), frame.candidates)
        assignments = []
        for candidate in frame.candidates:
            tid = int(candidate.source_detection_ids[0].split(':')[-1])
            boxes[tid] = candidate.measurement.bbox
            assignments.append((candidate.candidate_id, tid))
        response = BackendUpdate(tuple(assignments), tuple((tid, None if state == 'no_box' else boxes[tid]) for tid, state in states.items()))
        backend.update = lambda frame, response=response: response
        tracked = session.update(frame)
        records.append(json.loads(json.dumps({**tracking_record(tracked, session.events, config), 'run_id': 'synthetic-run'})))
    return records, video


def trace_from_records(records, video):
    """Construeix contractes de lectura reals per provar fragmentació sense E/S ni ffprobe."""
    return TrackingTrace(video.video_id, 'synthetic-run', tuple(_frame(record, video, 'synthetic-run', i) for i, record in enumerate(records)))


def write_tracking_export(root, pattern=None, timestamps=None):
    """Publica un informe i JSONL compatibles amb track; el vídeo es genera a les proves visuals."""
    root = Path(root)
    records, video = records_and_video(root, pattern, timestamps)
    tracks, report_path = root/'tracks.jsonl', root/'tracking.json'
    tracks.write_text(''.join(json.dumps(row)+'\n' for row in records), encoding='utf-8')
    report = {'schema_version': '1.0', 'task': 'track_recorded_detections', 'software_version': '0.5.0',
              'run_id': 'synthetic-run', 'case_id': video.video_id,
              'inputs': {'video': {'path': str(video.path), 'sha256': None}},
              'artifacts': {'frames_jsonl': str(tracks)},
              'range': {'first_frame_index': 0, 'last_frame_index': video.frame_count-1, 'warmup_frames': 0,
                        'tracker_started_at_frame': 0, 'source_start_s': 0., 'source_end_s': video.duration_s},
              'totals': {'frames': video.frame_count},
              'right_censored_track_ids': sorted(s['track_id'] for s in records[-1]['tracks'] if s['state'] != 'finished')}
    report_path.write_text(json.dumps(report), encoding='utf-8')
    return report_path, tracks, video, records
