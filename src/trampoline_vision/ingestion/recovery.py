"""Lector del JSONL de tracking complet: valida cobertura, run i vida d'identitats.

Consumeix l'informe publicat per track i contrasta cada frame amb el vídeo
original sondejat. No torna a executar trackers, models ni lectura de pose.
La procedència es conserva però no implica verificació visual d'identitat.
"""

from dataclasses import dataclass
import hashlib
import math
from pathlib import Path

from trampoline_vision.contracts.geometry import BoundingBox
from trampoline_vision.contracts.observations import DetectionProvenance, FrameContext
from trampoline_vision.contracts.recovery import TraceCandidate, TraceEvent, TrackingTraceFrame, TrackingTrace, identifier
from trampoline_vision.contracts.tracking import BoxMeasurement, TrackingCandidate, TrackSample
from trampoline_vision.ingestion.errors import InputError
from trampoline_vision.ingestion.json_io import parse_json
from trampoline_vision.recovery.errors import RecoveryError
from trampoline_vision.recovery.validation import validate_lifecycle


@dataclass(frozen=True)
class LoadedTrackingTrace:
    """Traça i metadades d'entrada amb hashes dels bytes efectivament llegits."""

    trace: TrackingTrace
    report: dict
    report_sha256: str
    frames_sha256: str


def sha256_file(path):
    """Calcula contingut en blocs, sense carregar vídeos sencers en memòria."""
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read_tracking_report(path):
    """Llegeix l'informe una vegada i en retorna objecte i SHA, rebutjant altres tasques."""
    try:
        raw = Path(path).read_bytes()
        report = parse_json(raw.decode('utf-8-sig'), str(path))
        if report.get('schema_version') != '1.0' or report.get('task') != 'track_recorded_detections':
            raise ValueError('Expected schema 1.0 report from track command')
        identifier(report['run_id'], 'run_id')
        identifier(report['case_id'], 'case_id')
        return report, hashlib.sha256(raw).hexdigest()
    except (InputError, OSError, UnicodeError, KeyError, TypeError, ValueError) as exc:
        raise RecoveryError(f'Invalid tracking report {path}: {exc}') from exc


def report_path(report_file, value):
    """Resol una ruta declarada; els overrides de CLI permeten moure artefactes entre equips."""
    identifier(value, 'input path')
    return (Path(report_file).resolve().parent / value).resolve()


def _object(value, required, optional=()):
    """Exigeix objectes amb claus conegudes per evitar ignorar evidència incompatible."""
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise ValueError(f'Expected fields {sorted(required)}; received incompatible object')
    return value


def _array(value):
    """Rebutja strings i objectes on l'esquema requereix una llista JSON."""
    if not isinstance(value, list):
        raise ValueError('Expected JSON array')
    return value


def _integer(value, name, minimum=0):
    """Rebutja booleans i decimals en recomptes i índexs."""
    if type(value) is not int or value < minimum:
        raise ValueError(f'{name} must be an integer >= {minimum}')
    return value


def _number(value, name, positive=False):
    """Valida nombres de temps finits, sense interpretar textos numèrics."""
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0 or positive and value == 0:
        raise ValueError(f'Invalid {name}')
    return value


def _box(value):
    """Recrea la geometria exacta, admetent prediccions fora de la imatge."""
    if value is None:
        return None
    return BoundingBox(**_object(value, ('x_min', 'y_min', 'x_max', 'y_max')))


def _candidate(value):
    """Converteix candidat/procedència sense fabricar PersonDetection ni keypoints."""
    value = _object(value, ('candidate_id', 'source_detection_ids', 'measurement', 'issues', 'provenance'), ('unassigned_reason',))
    measurement = value['measurement']
    if measurement is not None:
        measurement = _object(measurement, ('bbox', 'source', 'score', 'score_method'))
        measurement = BoxMeasurement(_box(measurement['bbox']), measurement['source'], measurement['score'], measurement['score_method'])
    candidate = TrackingCandidate(value['candidate_id'], tuple(_array(value['source_detection_ids'])), measurement, tuple(_array(value['issues'])))
    provenance = tuple(DetectionProvenance(**_object(p, ('source_path', 'source_record', 'source_frame_index', 'source_person_index', 'variant', 'rotation_provenance'))) for p in _array(value['provenance']))
    return TraceCandidate(candidate, provenance, value.get('unassigned_reason'))


def _frame(value, video, run_id, index):
    """Valida cada context contra ffprobe i converteix les mostres i els esdeveniments."""
    value = _object(value, ('schema_version', 'context', 'source_status', 'source_detections', 'candidates', 'tracks', 'unassigned_candidate_ids', 'events', 'run_id'))
    if value['schema_version'] != '1.0' or value['run_id'] != run_id:
        raise ValueError('Mixed tracking schema or run_id')
    ctx = _object(value['context'], ('video_id', 'frame_index', 'timestamp_s', 'duration_s', 'width_px', 'height_px'))
    for name in ('frame_index', 'width_px', 'height_px'):
        _integer(ctx[name], name, 0 if name == 'frame_index' else 1)
    _number(ctx['timestamp_s'], 'timestamp_s')
    _number(ctx['duration_s'], 'duration_s', positive=True)
    context = FrameContext(**ctx)
    expected = video.frame(index)
    if (context.video_id, context.frame_index, context.width_px, context.height_px) != (expected.video_id, index, expected.width_px, expected.height_px):
        raise ValueError('Frame index/video/geometry differs from source video')
    if abs(context.timestamp_s - expected.timestamp_s) > 1e-6 or abs(context.duration_s - expected.duration_s) > 1e-6:
        raise ValueError('Frame timing differs from source video')
    tracks = []
    for item in _array(value['tracks']):
        item = _object(item, ('track_id', 'state', 'evidence', 'bbox', 'candidate_id', 'last_observed_timestamp_s'))
        _number(item['last_observed_timestamp_s'], 'last_observed_timestamp_s')
        tracks.append(TrackSample(**{**item, 'bbox': _box(item['bbox'])}))
    events = tuple(TraceEvent(**_object(e, ('track_id', 'kind', 'timestamp_s'))) for e in _array(value['events']))
    return TrackingTraceFrame(context, value['source_status'], value['source_detections'],
        tuple(_candidate(c) for c in _array(value['candidates'])), tuple(tracks),
        tuple(_array(value['unassigned_candidate_ids'])), events)


def load_tracking_trace(tracks_path, report_file, video, *, report_data=None):
    """Exigeix cobertura completa i llegibilitat fins a EOF abans de retornar una traça.

Un interval parcial, una línia corrupta tardana o un ID reutilitzat invalida
tota la lectura. Els timestamps reals es preserven; no es remostregen FPS.
report_data permet que application usi exactament els mateixos bytes de report.
"""
    try:
        report, report_sha = report_data or read_tracking_report(report_file)
        if report['case_id'] != video.video_id:
            raise ValueError('Report and video identity differ')
        span, totals = report['range'], report['totals']
        for key, expected in (('first_frame_index', 0), ('last_frame_index', video.frame_count-1), ('warmup_frames', 0), ('tracker_started_at_frame', 0)):
            if _integer(span[key], key) != expected:
                raise ValueError('Recovery preparation requires a complete tracking export, not a partial interval')
        if _integer(totals['frames'], 'frames') != video.frame_count or _number(span['source_start_s'], 'source_start_s') != 0 or abs(_number(span['source_end_s'], 'source_end_s') - video.duration_s) > 1e-6:
            raise ValueError('Report coverage differs from complete source video')
        frames, digest = [], hashlib.sha256()
        with Path(tracks_path).open('rb') as stream:
            for line_number, raw in enumerate(stream, 1):
                digest.update(raw)
                if len(frames) >= video.frame_count:
                    raise ValueError('Extra JSONL frames after source video end')
                record = parse_json(raw.decode('utf-8-sig' if line_number == 1 else 'utf-8'), f'{tracks_path}:{line_number}')
                frames.append(_frame(record, video, report['run_id'], len(frames)))
        if len(frames) != video.frame_count:
            raise ValueError('Incomplete JSONL coverage')
        trace = TrackingTrace(video.video_id, report['run_id'], tuple(frames))
        alive = validate_lifecycle(trace)
        censored = _array(report['right_censored_track_ids'])
        if len(set(censored)) != len(censored) or set(censored) != set(alive):
            raise ValueError('Report right-censored IDs differ from final live tracks')
        observed = sum(s.evidence == 'observed' for f in frames for s in f.tracks)
        predicted = sum(s.state == 'lost' for f in frames for s in f.tracks)
        checks = {'source_detections': sum(f.source_detections for f in frames), 'candidates': sum(len(f.candidates) for f in frames),
                  'observed_track_samples': observed, 'predicted_track_samples': predicted,
                  'unassigned_candidates': sum(len(f.unassigned_candidate_ids) for f in frames),
                  'missing_source_frames': sum(f.source_status == 'missing' for f in frames)}
        # Alguns informes ometen comptadors zero: comparem només els camps declarats.
        for key, expected in checks.items():
            if key in totals and _integer(totals[key], key) != expected:
                raise ValueError(f'Report total differs: {key}')
        declared_sha = report.get('artifacts', {}).get('frames_sha256')
        if declared_sha is not None and declared_sha != digest.hexdigest():
            raise ValueError('Tracking JSONL checksum differs from report')
        return LoadedTrackingTrace(trace, report, report_sha, digest.hexdigest())
    except (InputError, OSError, UnicodeError, KeyError, TypeError, ValueError, IndexError, AttributeError) as exc:
        raise RecoveryError(f'Invalid tracking trace {tracks_path}: {exc}') from exc
