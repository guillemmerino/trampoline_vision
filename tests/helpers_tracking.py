"""Fixtures de seguiment sintètiques amb geometria de pose suficient i identitats controlades."""

from trampoline_vision.contracts.observations import (
    BODY25_NAMES, DetectionProvenance, FrameContext, FrameDetections, KeypointObservation, PersonDetection,
)
from trampoline_vision.preparation.pipeline import prepare_frame


def pose_values(dx=0, confidence=0.8):
    """Genera BODY_25 de mida 64×48, amb tronc i cames visibles; dx desplaça la persona."""
    coordinates = {"neck": (32, 6), "right_shoulder": (24, 10), "left_shoulder": (40, 10),
                   "mid_hip": (32, 22), "right_knee": (28, 34), "left_knee": (36, 34),
                   "right_ankle": (28, 44), "left_ankle": (36, 44)}
    return [value for name in BODY25_NAMES for value in
            ((coordinates[name][0] + dx, coordinates[name][1], confidence) if name in coordinates else (0, 0, 0))]


def tracking_frame(index=0, timestamp=0, people=("a",), status="present", video_id="test-case"):
    """Prepara un instant canònic sense vídeo, amb ID de detecció estable entre configuracions."""
    detections = []
    for person in people:
        values = pose_values()
        points = tuple(KeypointObservation(name, values[i * 3] if values[i * 3 + 2] else None,
                                          values[i * 3 + 1] if values[i * 3 + 2] else None,
                                          values[i * 3 + 2], bool(values[i * 3 + 2]), True if values[i * 3 + 2] else None)
                       for i, name in enumerate(BODY25_NAMES))
        provenance = DetectionProvenance("synthetic.zip", f"frame_{index + 1}.json", index + 1, 0, "synthetic", "unknown")
        detections.append(PersonDetection(person, points, provenance))
    return prepare_frame(FrameDetections(FrameContext(video_id, index, timestamp, 0.04, 64, 48), tuple(detections), status))
