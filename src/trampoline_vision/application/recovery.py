"""Cas d'ús independent: tracking acabat → fragments verificats → artefactes nous.

No executa detector, tracker, ReID ni associació d'actors. La lectura valida
tot el vídeo abans de publicar resultats; la visualització és opcional.
"""

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from uuid import uuid4

from trampoline_vision import __version__
from trampoline_vision.application.visualization import validate_rendered_video
from trampoline_vision.infrastructure.artifacts import publish_exclusive
from trampoline_vision.ingestion.recovery import load_tracking_trace, read_tracking_report, report_path, sha256_file
from trampoline_vision.ingestion.video import probe_video
from trampoline_vision.recovery.config import FragmentationConfig
from trampoline_vision.recovery.errors import RecoveryError
from trampoline_vision.recovery.pipeline import prepare_recovery
from trampoline_vision.results.overlay import RenderStyle
from trampoline_vision.results.recovery import diagnostics, fragment_record, gap_record, annotated_frames, render_fragment_frame
from trampoline_vision.results.video import encode_visualization


def inspect_tracking_fragments(report_file, output, *, tracks_path=None, video_path=None, fragments_output=None,
                               video_output=None, config=FragmentationConfig(), ffprobe='ffprobe',
                               probe_timeout_s=120, progress=None, protected_paths=()):
    """Valida informe/JSONL complets, fragmenta i publica informe, JSONL i MP4 opcional.

Els overrides de rutes permeten consumir informes generats dins d'un altre
contenidor/equip. El vídeo es sondeja sempre per provar cobertura completa.
Els SHA registren aquests inputs, però els informes antics sense hashes no
permeten provar retroactivament els píxels que van originar les deteccions.
"""
    report_file, output = Path(report_file).resolve(), Path(output).resolve()
    report_data = read_tracking_report(report_file)
    report, _ = report_data
    try:
        tracks_path = Path(tracks_path).resolve() if tracks_path else report_path(report_file, report['artifacts']['frames_jsonl'])
        video_path = Path(video_path).resolve() if video_path else report_path(report_file, report['inputs']['video']['path'])
    except (KeyError, TypeError, ValueError) as exc:
        raise RecoveryError(f'Tracking report lacks input paths: {exc}') from exc
    fragments_output = Path(fragments_output).resolve() if fragments_output else output.with_suffix('.fragments.jsonl')
    video_output = Path(video_output).resolve() if video_output else None
    destinations = [fragments_output, output] + ([video_output] if video_output else [])
    protected = {report_file, tracks_path, video_path, *(Path(p).resolve() for p in protected_paths)}
    # També protegeix fonts declarades, encara que el diagnòstic no necessiti tornar-les a llegir.
    for entry in report.get('inputs', {}).values():
        if isinstance(entry, dict) and isinstance(entry.get('path'), str):
            protected.add(report_path(report_file, entry['path']))
    if len(set(destinations)) != len(destinations) or video_output and video_output.suffix.lower() != '.mp4':
        raise RecoveryError('Choose distinct report/JSONL outputs and optional MP4')
    for path in destinations:
        if path.exists() or path in protected:
            raise RecoveryError(f'Refusing to overwrite recovery input or existing output: {path}')
    video = probe_video(video_path, report['case_id'], ffprobe=ffprobe, timeout_s=probe_timeout_s)
    loaded = load_tracking_trace(tracks_path, report_file, video, report_data=report_data)
    video_sha = sha256_file(video_path)
    declared_sha = report.get('inputs', {}).get('video', {}).get('sha256')
    if declared_sha is not None and declared_sha != video_sha:
        raise RecoveryError('Source video content hash differs from tracking report')
    result = prepare_recovery(loaded.trace, config)
    for path in destinations:
        path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='trampoline-fragments-') as temporary:
        root = Path(temporary)
        staged_jsonl, staged_report, staged_video = root/'fragments.jsonl', root/'report.json', root/'review.mp4'
        with staged_jsonl.open('w', encoding='utf-8', newline='\n') as stream:
            for kind, blocks, serialize in (('fragment', result.fragments, fragment_record), ('gap', result.gaps, gap_record)):
                for block in blocks:
                    record = {'schema_version': '1.0', 'record_type': kind, 'video_id': loaded.trace.video_id,
                              'tracking_run_id': loaded.trace.run_id, **serialize(block)}
                    stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False)+'\n')
        validation = {'complete_video_coverage_verified': True, 'track_lifecycle_verified': True,
                      'sample_partition_verified': True if config.enabled else None, 'visual_alignment_status': 'not_rendered'}
        if video_output:
            style = RenderStyle(view='all', min_confidence=0, min_visible_points=1)
            encode_visualization(video, annotated_frames(result, enabled=config.enabled), staged_video, style,
                                 0, video.frame_count, progress, renderer=render_fragment_frame)
            rendered = probe_video(staged_video, video.video_id, ffprobe=ffprobe, timeout_s=probe_timeout_s)
            validation.update(validate_rendered_video(video, rendered, 0, video.frame_count, style))
        summary = {'schema_version': '1.0', 'task': 'inspect_tracking_fragments', 'software_version': __version__,
                   'run_id': str(uuid4()), 'created_at': datetime.now(timezone.utc).isoformat(),
                   'video_id': video.video_id, 'tracking_run_id': loaded.trace.run_id,
                   'tracking_software_version': report.get('software_version', 'unknown'),
                   'effective_config': asdict(config), 'execution': 'offline_complete_video',
                   'inputs': {'tracking_report': {'path': str(report_file), 'sha256': loaded.report_sha256},
                              'tracks': {'path': str(tracks_path), 'sha256': loaded.frames_sha256},
                              'video': {'path': str(video_path), 'sha256': video_sha}},
                   'coverage': {'first_frame_index': 0, 'last_frame_index': video.frame_count-1,
                                'frame_count': video.frame_count, 'duration_s': video.duration_s},
                   **diagnostics(result, enabled=config.enabled), 'validation': validation,
                   'artifacts': {'fragments_jsonl': str(fragments_output), 'fragments_sha256': sha256_file(staged_jsonl),
                                 'video': str(video_output) if video_output else None},
                   'warnings': ['fragmentation_is_not_actor_recovery', 'box_center_is_not_center_of_mass',
                                'same_track_may_contain_actor_transfers_not_detected'] + list(video.warnings),
                   'capabilities_not_executed': ['link_proposals', 'global_association', 'actor_assignment',
                       'appearance_inference', 'identity_switch_detection', 'pose_matching', 'subject_selection', 'scoring'],
                   'next_steps': ['4_generate_link_proposals_in_audit', '5_appearance_global_assignment_and_chain_validation',
                                  '6_independent_evaluation_before_apply']}
        if declared_sha is None:
            summary['warnings'].append('legacy_tracking_report_has_no_video_content_hash_original_pixel_binding_unproven')
        if not report.get('artifacts', {}).get('frames_sha256'):
            summary['warnings'].append('legacy_tracking_report_has_no_jsonl_checksum')
        staged_report.write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
        staged = [(staged_jsonl, fragments_output)] + ([(staged_video, video_output)] if video_output else []) + [(staged_report, output)]
        published = []
        try:
            for source, destination in staged:
                publish_exclusive(source, destination)
                published.append(destination)
        except Exception:
            for path in published:
                path.unlink(missing_ok=True)
            raise
    return summary
