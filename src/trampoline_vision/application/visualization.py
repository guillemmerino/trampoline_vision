"""Cas d'ús de revisió visual del pas 3, reutilitzant els contractes d'ingestió."""

from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import version
import json
import math
from pathlib import Path
import tempfile
import time
from typing import Callable
from uuid import uuid4

from trampoline_vision import __version__
from trampoline_vision.contracts.observations import VideoAsset
from trampoline_vision.infrastructure.artifacts import publish_exclusive
from trampoline_vision.ingestion.manifest import CaseManifest
from trampoline_vision.ingestion.detections import iter_recorded_frames
from trampoline_vision.ingestion.video import probe_video
from trampoline_vision.results.errors import VisualizationError
from trampoline_vision.results.overlay import HEADER_HEIGHT, RenderStyle, output_dimensions
from trampoline_vision.results.video import encode_visualization


def select_frame_range(video: VideoAsset, start_s: float, end_s: float | None) -> tuple[int, int]:
    """Selecciona fotogrames per inici de presentació dins de [start_s, end_s).

    No s'inventa un fotograma al límit de tall. El resultat declara l'interval
    real mostrat, que pot diferir lleument del demanat per la quantització temporal.
    """
    end = video.duration_s if end_s is None else end_s
    if not math.isfinite(start_s) or not math.isfinite(end) or start_s < 0 or end <= start_s or end > video.duration_s + 0.000001:
        raise VisualizationError("Expected 0 <= start < end <= video duration")
    selected = [i for i, timestamp in enumerate(video.timestamps_s) if start_s <= timestamp < end]
    if not selected:
        raise VisualizationError("Requested time interval contains no frame presentation starts")
    return selected[0], selected[-1] + 1


def validate_rendered_video(source: VideoAsset, rendered: VideoAsset, first: int, stop: int,
                            style: RenderStyle) -> dict:
    """Contrasta la sortida descodificada amb l'interval original abans de publicar-la.

    Comprova recompte, dimensions, cada temps de presentació i durada final.
    Això valida la recodificació; la correcció anatòmica i la correspondència
    dels JSON amb les persones continuen requerint revisió humana.
    """
    if rendered.frame_count != stop - first:
        raise VisualizationError("Rendered video lost or duplicated frames")
    if (rendered.width_px, rendered.height_px) != output_dimensions(source.width_px, source.height_px, style):
        raise VisualizationError("Rendered dimensions do not match declared panel layout")
    expected_times = [source.timestamps_s[i] - source.timestamps_s[first] for i in range(first, stop)]
    errors = [abs(a - b) for a, b in zip(expected_times, rendered.timestamps_s)]
    expected_duration = source.timestamps_s[stop - 1] - source.timestamps_s[first] + source.frame_durations_s[stop - 1]
    duration_error = abs(rendered.duration_s - expected_duration)
    if max(errors) > 0.0001 or duration_error > 0.0001:
        raise VisualizationError("Rendered timestamps or duration differ from the source interval")
    return {"frame_count_verified": True, "timestamps_verified": True,
            "max_timestamp_error_s": max(errors), "duration_error_s": duration_error,
            "visual_alignment_status": "pending_human_review"}


def visualize_case(manifest: CaseManifest, video: VideoAsset, output: Path, report: Path, *,
                   style: RenderStyle = RenderStyle(), start_s: float = 0.0, end_s: float | None = None,
                   missing_frames_policy: str = "report", ffprobe: str = "ffprobe", probe_timeout_s: float = 120,
                   progress: Callable[[int, int], None] | None = None, protected_paths: tuple[Path, ...] = ()) -> dict:
    """Renderitza i verifica MP4 + informe JSON, conservant els originals.

    La selecció temporal i els filtres només afecten els artefactes de revisió.
    Els fitxers finals no es publiquen fins a completar lectura, codificació
    i sondeig de sortida. L'informe es publica l'últim com a confirmació del cas.
    """
    started = time.perf_counter()
    output, report = output.resolve(), report.resolve()
    protected = {manifest.path, manifest.video_path, manifest.detections_path, *[p.resolve() for p in protected_paths]}
    if output.suffix.lower() != ".mp4" or output == report:
        raise VisualizationError("Choose an MP4 output and a separate report path")
    for path in (output, report):
        if path in protected or path.exists():
            raise VisualizationError(f"Refusing to overwrite input or existing output: {path}")
    first, stop = select_frame_range(video, start_s, end_s)
    for path in (output, report):
        path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="trampoline-visualize-") as temporary:
        staged_video = Path(temporary) / "annotated.mp4"
        with closing(iter_recorded_frames(manifest, video, missing_frames_policy=missing_frames_policy)) as observations:
            details = encode_visualization(video, observations, staged_video, style, first, stop, progress)
        rendered = probe_video(staged_video, manifest.case_id, ffprobe=ffprobe, timeout_s=probe_timeout_s)
        validation = validate_rendered_video(video, rendered, first, stop, style)
        source_end = video.timestamps_s[stop - 1] + video.frame_durations_s[stop - 1]
        warnings = [{"code": w} for w in video.warnings]
        if manifest.declared_reference_duration_s is not None and abs(manifest.declared_reference_duration_s - video.duration_s) > 0.001:
            warnings.append({"code": "reference_duration_mismatch", "declared_s": manifest.declared_reference_duration_s, "video_s": video.duration_s})
        missing = sum(frame["source_status"] == "missing" for frame in details["frames"])
        if missing:
            warnings.append({"code": "missing_source_records_in_rendered_interval", "count": missing})
        result = {
            "schema_version": "1.0", "task": "visualize_recorded_detections", "run_id": str(uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat(), "software_version": __version__,
            "case_id": manifest.case_id, "inputs": {"manifest": str(manifest.path), "video": str(video.path), "detections": str(manifest.detections_path)},
            "style": asdict(style), "missing_frames_policy": missing_frames_policy,
            "range": {"requested_start_s": start_s, "requested_end_s": end_s, "first_frame_index": first,
                      "last_frame_index": stop - 1, "source_start_s": video.timestamps_s[first], "source_end_s": source_end},
            "output_video": {"path": str(output), "frame_count": rendered.frame_count, "duration_s": rendered.duration_s,
                             "width_px": rendered.width_px, "height_px": rendered.height_px, "audio": "omitted_for_diagnostic_video"},
            "layout": {"source_width_px": video.width_px, "source_height_px": video.height_px,
                       "header_height_px": HEADER_HEIGHT, "scale": 1,
                       "panels": [{"view": view, "x_px": index * video.width_px, "y_px": HEADER_HEIGHT}
                                  for index, view in enumerate(("all", "filtered") if style.view == "compare" else (style.view,))]},
            "validation": validation, "warnings": warnings, "known_input_issues": list(manifest.known_issues),
            "dependencies": {"av": version("av"), "Pillow": version("Pillow")},
            "capabilities_not_executed": ["inference", "deduplication", "tracking", "subject_selection", "segmentation", "scoring"],
            "elapsed_s": time.perf_counter() - started, **details,
        }
        staged_report = Path(temporary) / "report.json"
        staged_report.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        publish_exclusive(staged_video, output)
        publish_exclusive(staged_report, report)
    return result
