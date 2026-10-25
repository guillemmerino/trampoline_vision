"""Adaptador d'OC-SORT: únic lloc que coneix NumPy, Supervision i trackers.

La resta del domini consumeix BackendUpdate i els contractes propis. Només
s'utilitzen update i tracked_objects públics de la versió fixada.
"""

from dataclasses import dataclass
from importlib.metadata import version

from trampoline_vision.contracts.tracking import BoundingBox, TrackingFrame
from trampoline_vision.tracking.config import TrackerConfig
from trampoline_vision.tracking.errors import TrackingError


@dataclass(frozen=True)
class BackendUpdate:
    """Resposta normalitzada: assignacions actuals i caixes estimades de totes les identitats vives."""

    assignments: tuple[tuple[str, int], ...]  # candidate_id -> ID extern; -1 encara sense ID públic del backend.
    alive: tuple[tuple[int, BoundingBox | None], ...]  # ID extern -> estimació; la sessió decideix confirmació de domini.


class OCSortBackend:
    """Una instància d'OC-SORT per execució i vídeo; no carrega pesos ni imatges."""

    def __init__(self, config: TrackerConfig, nominal_fps: float):
        """Carrega l'extra opcional i fixa el pressupost temporal i els paràmetres efectius."""
        try:
            import numpy as np
            import supervision as sv
            from trackers import OCSORTTracker
        except (ImportError, OSError) as exc:
            raise TrackingError("Tracking requires trampoline-vision[tracking]; use the tracking Docker service.") from exc
        if version("trackers") != "2.6.1":
            raise TrackingError("Unsupported trackers version; install trackers==2.6.1")
        self.np, self.sv = np, sv
        self.tracker = OCSORTTracker(
            lost_track_buffer=config.lost_buffer, frame_rate=nominal_fps,
            # Amb 1, una mesura d'un ID existent sempre s'exposa en reapareixer.
            # La confirmació de naixements es gestiona a TrackingSession; no es
            # consulta estat privat ni es reconfirma cada recuperació.
            minimum_consecutive_frames=1,
            minimum_iou_threshold=config.min_iou,
            direction_consistency_weight=config.direction_weight,
            high_conf_det_threshold=config.confidence_threshold,
            delta_t=config.velocity_lookback_frames,
        )

    def update(self, frame: TrackingFrame) -> BackendUpdate:
        """Envia caixes mesurades amb confiança explícita i recupera correspondències per ID, no per ordre."""
        candidates = [c for c in frame.candidates if c.measurement is not None]
        np, sv = self.np, self.sv
        if candidates:
            boxes = [[c.measurement.bbox.x_min, c.measurement.bbox.y_min,
                      c.measurement.bbox.x_max, c.measurement.bbox.y_max] for c in candidates]
            detections = sv.Detections(xyxy=np.array(boxes, dtype=np.float64),
                                      confidence=np.array([c.measurement.score for c in candidates]),
                                      data={"candidate_id": np.array([c.candidate_id for c in candidates])})
        else:
            detections = sv.Detections.empty()
        try:
            result = self.tracker.update(detections, timestamp=frame.source.context.timestamp_s)
            assignments = tuple((str(cid), int(tid)) for cid, tid in
                                zip(result.data.get("candidate_id", []), result.tracker_id))
            alive = []
            predicted = self.tracker.tracked_objects
            for tid, row in zip(predicted.tracker_id, predicted.xyxy):
                try:
                    box = BoundingBox(*(float(v) for v in row))
                except ValueError:
                    box = None  # Es manté la identitat, però mai es dibuixa una estimació invàlida.
                alive.append((int(tid), box))
        except (ValueError, RuntimeError) as exc:
            raise TrackingError(f"OC-SORT update failed: {exc}") from exc
        return BackendUpdate(assignments, tuple(alive))
