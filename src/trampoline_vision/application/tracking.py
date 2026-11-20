"""Cas d'ús complet de seguiment enregistrat: preparar, associar, exportar i revisar.

Sense inferència de persones o poses ni puntuació. ReID pot extreure aparença.
Es pot invocar des de CLI i futures
interfícies; les sortides només es publiquen després de completar el tram.
"""

from collections import Counter
from contextlib import closing, ExitStack
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import time
from uuid import uuid4

from trampoline_vision import __version__
from trampoline_vision.application.appearance import AppearanceService
from trampoline_vision.application.visualization import select_frame_range, validate_rendered_video
from trampoline_vision.contracts.observations import VideoAsset
from trampoline_vision.infrastructure.artifacts import publish_exclusive
from trampoline_vision.ingestion.manifest import CaseManifest
from trampoline_vision.ingestion.detections import iter_recorded_frames
from trampoline_vision.ingestion.video import probe_video
from trampoline_vision.ingestion.video_frames import VideoFrameReader
from trampoline_vision.preparation.config import PreparationConfig
from trampoline_vision.preparation.pipeline import prepare_frame
from trampoline_vision.results.overlay import RenderStyle
from trampoline_vision.results.tracking import TrackingOverlayFrame, render_tracking_frame, tracking_record
from trampoline_vision.results.video import encode_visualization
from trampoline_vision.tracking.config import TrackerConfig
from trampoline_vision.tracking.errors import TrackingError
from trampoline_vision.tracking.session import TrackingSession


def _input_identity(path: Path) -> dict:
    """Registra ruta, mida i mtime sense hashejar vídeos grans; JSON petits sí que tenen hash de contingut."""
    stat = path.stat()
    return {"path": str(path), "size_bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.suffix.lower() == ".json" else None}


def track_case(manifest: CaseManifest, video: VideoAsset, output: Path, frames_output: Path, *,
               preparation: PreparationConfig = PreparationConfig(), tracker: TrackerConfig = TrackerConfig(),
               video_output: Path | None = None, start_s: float = 0.0, end_s: float | None = None,
               missing_frames_policy: str = "report", ffprobe: str = "ffprobe", probe_timeout_s: float = 120,
               progress=None, protected_paths: tuple[Path, ...] = ()) -> dict:
    """Produeix informe, JSONL temporalment complet i MP4 opcional sense sobreescriure entrades.

    En intervals, el tracker s'escalfa des del fotograma zero fins al primer
    instant seleccionat. El JSONL només exporta l'interval demanat, amb temps
    originals. Les identitats vives al final són censurades, no finalitzades
    artificialment. No s'utilitza informació posterior al límit end_s.
    """
    started, run_id = time.perf_counter(), str(uuid4())
    if video.video_id != manifest.case_id or video.path.resolve() != manifest.video_path.resolve():
        raise TrackingError("Video and manifest must describe the same input")
    output, frames_output = output.resolve(), frames_output.resolve()
    video_output = video_output.resolve() if video_output else None
    destinations = [frames_output, output] + ([video_output] if video_output else [])
    if len(set(destinations)) != len(destinations) or (video_output and video_output.suffix.lower() != ".mp4"):
        raise TrackingError("Choose distinct report, JSONL and optional MP4 outputs")
    protected = {manifest.path.resolve(), manifest.video_path.resolve(), manifest.detections_path.resolve(),
                 *[p.resolve() for p in protected_paths]}
    for path in destinations:
        if (path in protected or path.exists()
                or (manifest.detections_path.is_dir() and path.is_relative_to(manifest.detections_path.resolve()))):
            raise TrackingError(f"Refusing to overwrite input or existing output: {path}")
    if preparation.representative_boxes is not None and manifest.detections_format != "person_boxes_csv":
        raise TrackingError("Representative box preparation requires a person_boxes_csv manifest")
    if tracker.appearance is not None:
        if manifest.detections_format != "person_boxes_csv":
            raise TrackingError("ReID profiles require independent person_boxes_csv input; pose matching is a later stage")
        protected.add(Path(tracker.appearance.weights).resolve())
        if any(path in protected for path in destinations):
            raise TrackingError("Tracking outputs cannot replace appearance weights")
        if tracker.appearance.cache_dir:
            cache_root = Path(tracker.appearance.cache_dir).resolve()
            if any(path.is_relative_to(cache_root) for path in destinations):
                raise TrackingError("Tracking outputs must stay outside the appearance cache directory")
    first, stop = select_frame_range(video, start_s, end_s)
    nominal_fps = video.fps or 1 / video.frame_durations_s[0]
    if tracker.backend == "botsort" and any(abs(dt - 1 / nominal_fps) > .0001 for dt in video.frame_durations_s):
        raise TrackingError("BoT-SORT currently requires constant frame timing; use OC-SORT or ByteTrack for VFR")
    session = TrackingSession(tracker, nominal_fps)
    totals, issues, unassigned_reasons, event_counts = Counter(), Counter(), Counter(), Counter()
    summaries = {}
    style = RenderStyle(view="all", min_confidence=0, min_visible_points=1)
    with ExitStack() as resources:
        representative, reader, background_indices = None, None, ()
        if preparation.representative_boxes is not None:
            try:
                from trampoline_vision.preparation.foreground import sample_indices
                from trampoline_vision.preparation.representative import RepresentativeBoxPreparer
            except ImportError as exc:
                raise TrackingError("Install trampoline-vision[box-preparation] for silhouette ranking") from exc
            background_indices = sample_indices(stop)
            with closing(VideoFrameReader(video)) as background_reader:
                representative = RepresentativeBoxPreparer(
                    video.video_id, preparation,
                    (background_reader.get(i).to_ndarray(format="bgr24") for i in background_indices),
                )
            if not video_output:
                reader = resources.enter_context(closing(VideoFrameReader(video)))
        appearance = (AppearanceService(tracker.appearance, video, manifest, preparation,
                                        background_indices=background_indices) if tracker.appearance else None)
        if appearance:
            resources.callback(appearance.close)
        for path in destinations:
            path.parent.mkdir(parents=True, exist_ok=True)
        temporary = resources.enter_context(tempfile.TemporaryDirectory(prefix="trampoline-track-"))
        temp = Path(temporary)
        staged_frames, staged_video, staged_report = temp / "tracks.jsonl", temp / "tracks.mp4", temp / "report.json"
        # El descodificador de visualització comparteix el fotograma amb preparació i aparença.
        decoded_frame = None

        def supply_decoded(index, decoded):
            """Comparteix el fotograma validat de visualització amb preparació i aparença."""
            nonlocal decoded_frame
            decoded_frame = (index, decoded)
            if appearance:
                appearance.supply_decoded(index, decoded)

        with staged_frames.open("w", encoding="utf-8", newline="\n") as stream:

            def tracked_frames():
                """Consumeix observacions fins al límit, registra mètriques seleccionades i allibera el ZIP en errors."""
                with closing(iter_recorded_frames(manifest, video, missing_frames_policy=missing_frames_policy)) as raw_frames:
                    for index in range(stop):
                        source = next(raw_frames)
                        if representative is None:
                            prepared = prepare_frame(source, preparation)
                        else:
                            if reader is not None:
                                decoded = reader.get(index)
                                if appearance:
                                    appearance.supply_decoded(index, decoded)
                            else:
                                if decoded_frame is None or decoded_frame[0] != index:
                                    raise TrackingError("Silhouette preparation needs aligned decoded video frames")
                                decoded = decoded_frame[1]
                            prepared = prepare_frame(source, preparation, representative=representative,
                                                     image=decoded.to_ndarray(format="bgr24"))
                        descriptors = appearance.for_frame(prepared) if appearance else None
                        result = session.update(prepared, descriptors)
                        record = tracking_record(result, session.events, tracker)
                        record["run_id"] = run_id
                        for sample in result.tracks:
                            summary = summaries.setdefault(sample.track_id, {
                                "track_id": sample.track_id, "first_confirmed_frame": index,
                                "first_confirmed_s": source.context.timestamp_s, "observed_samples": 0,
                                "predicted_samples": 0, "last_observed_s": sample.last_observed_timestamp_s,
                                "last_state": sample.state, "max_unobserved_s": 0.0,
                            })
                            summary["last_state"] = sample.state
                            summary["last_observed_s"] = sample.last_observed_timestamp_s
                            summary["observed_samples" if sample.evidence == "observed" else "predicted_samples"] += sample.state != "finished"
                            summary["max_unobserved_s"] = max(summary["max_unobserved_s"], source.context.timestamp_s - sample.last_observed_timestamp_s)
                        if index >= first:
                            stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
                            totals["frames"] += 1
                            totals["missing_source_frames"] += source.source_status == "missing"
                            totals["source_detections"] += len(source.detections)
                            totals["candidates"] += len(result.frame.candidates)
                            totals["unassigned_candidates"] += len(result.unassigned_candidate_ids)
                            totals["observed_track_samples"] += sum(t.evidence == "observed" for t in result.tracks)
                            totals["predicted_track_samples"] += sum(t.state == "lost" for t in result.tracks)
                            for candidate in record["candidates"]:
                                issues.update(candidate["issues"])
                                if "unassigned_reason" in candidate:
                                    unassigned_reasons[candidate["unassigned_reason"]] += 1
                            event_counts.update(e.kind for e in session.events)
                            if progress and not video_output:
                                progress(index - first + 1, stop - first)
                        yield TrackingOverlayFrame(result)

            with closing(tracked_frames()) as annotated:
                if video_output:
                    encode_visualization(video, annotated, staged_video, style, first, stop, progress,
                                         renderer=render_tracking_frame, decoded_callback=supply_decoded if appearance or representative else None)
                else:
                    for _ in annotated:
                        pass
        validation = {"frame_sequence_verified": True, "identity_accuracy": "not_evaluated",
                      "visual_alignment_status": "pending_human_review"}
        output_video = None
        if video_output:
            rendered = probe_video(staged_video, manifest.case_id, ffprobe=ffprobe, timeout_s=probe_timeout_s)
            validation.update(validate_rendered_video(video, rendered, first, stop, style))
            output_video = {"path": str(video_output), "frame_count": rendered.frame_count,
                            "duration_s": rendered.duration_s, "audio": "omitted_for_diagnostic_video"}
        open_tracks = sorted(t.track_id for t in session.live.values())
        result = {
            "schema_version": "1.0", "task": "track_recorded_detections", "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(), "software_version": __version__,
            "case_id": manifest.case_id,
            "inputs": {"manifest": _input_identity(manifest.path), "video": _input_identity(video.path),
                       "detections": _input_identity(manifest.detections_path)},
            "effective_config": {"preparation": {"schema_version": "1.0", **asdict(preparation)},
                                 "tracker": asdict(tracker), "missing_frames_policy": missing_frames_policy},
            "backend": session.backend.describe(),
            "dependencies": session.backend.describe()["dependencies"],
            "appearance": appearance.describe() if appearance else None,
            "range": {"requested_start_s": start_s, "requested_end_s": end_s, "first_frame_index": first,
                      "last_frame_index": stop - 1, "warmup_frames": first, "tracker_started_at_frame": 0,
                      "source_start_s": video.timestamps_s[first],
                      "source_end_s": video.timestamps_s[stop - 1] + video.frame_durations_s[stop - 1]},
            "totals": dict(totals), "candidate_issues": dict(issues), "unassigned_reasons": dict(unassigned_reasons),
            "events_in_selected_range": dict(event_counts), "tracks_including_warmup": list(summaries.values()),
            "right_censored_track_ids": open_tracks, "validation": validation,
            "unconfirmed_external_tracks_at_end": len(session.pending),
            "artifacts": {"frames_jsonl": str(frames_output), "video": str(video_output) if video_output else None},
            "output_video": output_video, "known_input_issues": list(manifest.known_issues),
            "warnings": list(video.warnings) + ["thresholds_not_calibrated", "all_actors_tracked_no_gymnast_selection",
                                                "input_size_and_mtime_are_not_content_hashes"],
            "capabilities_not_executed": ["inference", "subject_selection", "segmentation", "scoring"],
            "elapsed_s": time.perf_counter() - started,
        }
        if representative:
            result["preparation_background"] = {"method": "fixed_median_half_resolution_v1",
                                                "sample_frame_indices": list(background_indices)}
        result["capabilities_executed"] = ["recorded_boxes_reading" if manifest.detections_format == "person_boxes_csv" else "legacy_pose_extent_reading", "tracking"]
        if representative:
            result["capabilities_executed"].append("silhouette_box_preparation")
        if appearance:
            result["capabilities_executed"].append("appearance_inference" if appearance.extracted_candidates else "appearance_cache")
            result["capabilities_not_executed"] = ["person_detector_inference", "pose_inference", "pose_matching", "actor_coherence", "subject_selection", "segmentation", "scoring"]
        if manifest.declared_reference_duration_s is not None and abs(manifest.declared_reference_duration_s - video.duration_s) > 0.001:
            result["warnings"].append("reference_duration_mismatch")
        staged_report.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        staged = [(staged_frames, frames_output)] + ([(staged_video, video_output)] if video_output else []) + [(staged_report, output)]
        published = []
        try:
            for source, destination in staged:
                publish_exclusive(source, destination)
                published.append(destination)
        except Exception:
            # Neteja només fitxers creats per aquesta publicació; un destí preexistent no s'elimina.
            for path in published:
                path.unlink(missing_ok=True)
            raise
    return result
