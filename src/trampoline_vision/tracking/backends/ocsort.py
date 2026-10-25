"""Adaptador OC-SORT 0.4.0 preservat dins de la interfície de backends configurable."""

from trampoline_vision.tracking.backends._arrays import ArrayBackend


class OCSortBackend(ArrayBackend):
    """Associa caixes sense imatges ni descriptors d'aparença."""

    name = "ocsort"

    def __init__(self, config, nominal_fps):
        """Tradueix el perfil i manté la confirmació de naixements al domini."""
        super().__init__(config, nominal_fps)
        from trackers import OCSORTTracker
        self.tracker = OCSORTTracker(
            lost_track_buffer=config.lost_buffer, frame_rate=nominal_fps,
            minimum_consecutive_frames=1, minimum_iou_threshold=config.min_iou,
            direction_consistency_weight=config.direction_weight,
            high_conf_det_threshold=config.confidence_threshold,
            delta_t=config.velocity_lookback_frames)
