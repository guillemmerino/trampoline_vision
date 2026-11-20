"""Preparació pública de caixes representatives amb silueta i fons fix."""

from collections.abc import Iterable

import numpy as np

from trampoline_vision.contracts.geometry import BoundingBox
from trampoline_vision.contracts.observations import FrameDetections, PersonBoxDetection
from trampoline_vision.contracts.tracking import BoxMeasurement, TrackingCandidate, TrackingFrame
from trampoline_vision.preparation.boxes import prepare_boxes
from trampoline_vision.preparation.config import PreparationConfig
from trampoline_vision.preparation.foreground import median_background, rank_regions, validate_pixels
from trampoline_vision.preparation.regions import group_regions


def _tracking_frame(base, shortlist):
    """Construeix les mesures actives i conserva el fotograma font complet."""
    detections = {d.detection_id: d for d in base.source.detections}
    candidates = []
    for region in shortlist:
        originals = tuple(ref for member in region.members for ref in base.candidates[member].source_detection_ids)
        if region.observed_region is None:
            representative = region.anchor_source_id
            kind = "support_extent"
            method = "support_extent_seed_detector_confidence"
            issues = ("pose_not_available", "derived_support_extent")
        else:
            representative = base.candidates[region.observed_region].source_detection_ids[0]
            kind = "detector"
            method = "recorded_detector_confidence"
            issues = ("pose_not_available",)
        refs = (representative, *(ref for ref in originals if ref != representative))
        candidates.append(TrackingCandidate(
            base.candidates[region.anchor].candidate_id, refs,
            BoxMeasurement(BoundingBox(*region.bbox), kind, detections[representative].score, method), issues,
        ))
    return TrackingFrame(base.source, tuple(candidates))


class RepresentativeBoxPreparer:
    """Reutilitza una zona calibrada i un fons immutable durant un vídeo.

    Rep píxels BGR alineats i caixes de persona enregistrades. Cada crida
    prepara un instant de manera independent. El tracker associa els IDs després.
    """

    def __init__(self, video_id: str, config: PreparationConfig, background_frames: Iterable[np.ndarray]):
        """Calcula el fons medià fix i converteix la zona normalitzada a píxels."""
        if not isinstance(video_id, str) or not video_id.strip():
            raise ValueError("Silhouette preparation requires a video ID")
        if not isinstance(config, PreparationConfig) or config.representative_boxes is None:
            raise ValueError("Silhouette preparation requires an enabled representative box profile")
        self.config = config
        self.video_id = video_id
        self._background, self._shape = median_background(background_frames)
        height, width, _ = self._shape
        self._zone = np.asarray(config.representative_boxes.zone) * (width, height, width, height)

    def prepare(self, source: FrameDetections, image: np.ndarray) -> TrackingFrame:
        """Prepara un fotograma alineat i retorna com a màxim el nombre de caixes configurat."""
        if not isinstance(source, FrameDetections) or any(
                not isinstance(d, PersonBoxDetection) for d in source.detections):
            raise ValueError("Silhouette preparation requires recorded person boxes")
        context = source.context
        if context.video_id != self.video_id or (context.height_px, context.width_px) != self._shape[:2]:
            raise ValueError("Detection frame does not match the silhouette background")
        validate_pixels(image, self._shape)
        if not source.detections:
            return TrackingFrame(source, ())
        base = prepare_boxes(source, self.config.box_preparation, include_relations=False)
        policy = self.config.representative_boxes
        ranked = rank_regions(group_regions(base), image, self._background, self._zone,
                              hard_zone=policy.zone_mode == "hard", limit=policy.max_candidates)
        return _tracking_frame(base, ranked)
