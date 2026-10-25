"""Despatx de fonts enregistrades cap als mateixos contractes de fotograma."""

from trampoline_vision.ingestion.errors import InputError


def iter_recorded_frames(manifest, video, *, missing_frames_policy="report"):
    """Selecciona lector de caixes o OpenPose; no associa fonts ni executa models."""
    if manifest.detections_format == "person_boxes_csv":
        from trampoline_vision.ingestion.recorded_boxes import iter_box_frames
        yield from iter_box_frames(manifest, video, missing_frames_policy=missing_frames_policy)
    elif manifest.detections_format in ("openpose_json_zip", "openpose_json_directory"):
        from trampoline_vision.ingestion.openpose import iter_openpose_frames
        yield from iter_openpose_frames(manifest, video, missing_frames_policy=missing_frames_policy)
    else:
        raise InputError("Unsupported recorded detection source")
