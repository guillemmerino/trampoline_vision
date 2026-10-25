"""Conversió comuna de caixes a l'API fixada de trackers, sense polítiques de vida."""

from importlib.metadata import version
from trampoline_vision.contracts.tracking import BoundingBox, TrackingFrame
from trampoline_vision.tracking.backend import BackendUpdate
from trampoline_vision.tracking.errors import TrackingError


class ArrayBackend:
    """Comparteix només transport NumPy/Supervision; cada adaptador construeix el seu tracker."""

    requires_appearance = False

    def __init__(self, config, nominal_fps):
        """Carrega dependències opcionals i rebutja una API no comprovada."""
        try:
            import numpy as np
            import supervision as sv
        except (ImportError, OSError) as exc:
            raise TrackingError("Install trampoline-vision[tracking] or use the tracking Docker service") from exc
        if version("trackers") != "2.6.1":
            raise TrackingError("Unsupported trackers version; install trackers==2.6.1")
        self.np, self.sv = np, sv
        self.config, self.nominal_fps = config, nominal_fps

    def describe(self):
        """Declara biblioteca, unitats i versions reals per a l'informe d'execució."""
        return {"name": self.name, "library": "trackers", "version": version("trackers"),
                "nominal_fps": self.nominal_fps, "minimum_consecutive_frames": 1,
                "confirmation_policy": self.config.confirmation_policy,
                "lost_buffer_30fps_units": self.config.lost_buffer,
                "retention_semantics": "backend_timestamp_api",
                "dependencies": {name: version(name) for name in ("trackers", "supervision", "numpy", "scipy")}}

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
            raise TrackingError(f"{self.name} update failed: {exc}") from exc
        return BackendUpdate(assignments, tuple(alive))
