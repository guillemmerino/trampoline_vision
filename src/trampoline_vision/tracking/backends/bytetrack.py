"""Adaptador ByteTrack amb llindar fort i admissió feble separats i auditables."""

from dataclasses import replace

from trampoline_vision.tracking.backend import BackendUpdate
from trampoline_vision.tracking.backends._arrays import ArrayBackend


class ByteTrackBackend(ArrayBackend):
    """Reutilitza la confirmació comuna; el backend pot associar evidència de confiança baixa."""

    name = "bytetrack"

    def __init__(self, config, nominal_fps):
        """Configura l'API fixada amb exposició immediata de matches ja coneguts."""
        super().__init__(config, nominal_fps)
        from trackers import ByteTrackTracker
        self.tracker = ByteTrackTracker(
            lost_track_buffer=config.lost_buffer, frame_rate=nominal_fps,
            track_activation_threshold=config.confidence_threshold,
            high_conf_det_threshold=config.confidence_threshold,
            minimum_consecutive_frames=1, minimum_iou_threshold=config.parameters.min_iou)

    def update(self, frame):
        """Conserva la partició completa encara que hi hagi caixes sota el llindar baix."""
        eligible = tuple(c for c in frame.candidates if c.measurement is None
                         or c.measurement.score >= self.config.parameters.low_confidence)
        ignored = tuple((c.candidate_id, -1) for c in frame.candidates if c.measurement is not None
                        and c.measurement.score < self.config.parameters.low_confidence)
        response = super().update(replace(frame, candidates=eligible))
        return BackendUpdate(response.assignments + ignored, response.alive)
