"""Port BoT-SORT fixat, amb descriptors externs i compensació d'identitat per càmera fixa.

No carrega detectors ni models de pose. L'aparença prové del domini
perception; els estats de vida públics els decideix TrackingSession.
"""

from contextlib import contextmanager
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path
import threading

from trampoline_vision.contracts.tracking import BoundingBox
from trampoline_vision.tracking.backend import BackendUpdate
from trampoline_vision.tracking.errors import TrackingError


_ID_LOCK = threading.RLock()  # La biblioteca 16.0.9 utilitza mètodes d'IDs globals; s'aïllen per instància.


class FixedCamera:
    """Component de compensació explícit per a l'escenari de càmera fixa implementat."""

    def apply(self, image, detections):
        """Retorna identitat; la imatge no s'usa per estimar moviment de càmera."""
        import numpy as np
        return np.array([[1., 0., 0.], [0., 1., 0.]])


class BotSortBackend:
    """Adapta candidats i descriptors a BoxMOT 16.0.9 sense inferència amagada."""

    name = "botsort"

    def __init__(self, config, nominal_fps):
        """Construeix associació i aïlla el comptador global d'IDs de cada vídeo."""
        try:
            import numpy as np
            import torch
            from boxmot import BotSort
            from boxmot.trackers.botsort.basetrack import BaseTrack
        except (ImportError, OSError) as exc:
            raise TrackingError("BoT-SORT requires trampoline-vision[tracking-reid] or the tracking-reid Docker service") from exc
        if version("boxmot") != "16.0.9":
            raise TrackingError("Unsupported BoxMOT version; install boxmot==16.0.9")
        self.np, self.base_track = np, BaseTrack
        self.config, self.nominal_fps = config, nominal_fps
        self.requires_appearance = config.appearance is not None
        self.counter, self.known = 0, set()
        self.previous_timestamp = None
        self.image = None
        parameters = asdict(config.parameters)
        low = parameters.pop("low_confidence")
        with self._identity_scope():
            # El component d'aparença és extern. Amb embs sempre explícits,
            # l'API fixada no necessita construir un segon model ReID intern.
            self.tracker = BotSort(
                reid_weights=Path("unused_external_embeddings.pt"), device=torch.device("cpu"), half=False,
                with_reid=False, track_high_thresh=config.confidence_threshold,
                track_low_thresh=low, new_track_thresh=config.confidence_threshold,
                track_buffer=config.lost_buffer, frame_rate=nominal_fps, **parameters)
        self.tracker.with_reid = self.requires_appearance
        self.tracker.cmc = FixedCamera()

    def _next_id(self):
        """Assigna IDs monotònics locals, sense reiniciar els d'una altra sessió."""
        self.counter += 1
        return self.counter

    @contextmanager
    def _identity_scope(self):
        """Aïlla els dos mètodes públics globals de BoxMOT només durant una operació bloquejada.

        L'adaptador mai modifica _count ni estat privat. Totes les instàncies
        d'aquest port comparteixen el bloqueig i restauren els mètodes en errors.
        """
        with _ID_LOCK:
            original_next, original_clear = self.base_track.next_id, self.base_track.clear_count
            self.base_track.next_id = staticmethod(self._next_id)
            self.base_track.clear_count = staticmethod(lambda: None)
            try:
                yield
            finally:
                self.base_track.next_id = staticmethod(original_next)
                self.base_track.clear_count = staticmethod(original_clear)

    def update(self, frame, appearance=None):
        """Associa per det_ind explícit i tradueix vida externa sense modificar caixes observades."""
        timestamp = frame.source.context.timestamp_s
        if self.previous_timestamp is not None and abs(timestamp - self.previous_timestamp - 1/self.nominal_fps) > .0001:
            raise TrackingError("BoT-SORT currently requires constant frame timing")
        candidates = [c for c in frame.candidates if c.measurement is not None]
        np = self.np
        embeddings = None
        if self.requires_appearance:
            if appearance is None or appearance.context != frame.source.context:
                raise TrackingError("BoT-SORT ReID requires appearance from the same frame")
            vectors = {e.candidate_id: e.values for e in appearance.embeddings}
            if set(vectors) != {c.candidate_id for c in candidates}:
                raise TrackingError("Appearance does not cover measured candidates exactly")
            dimension = len(appearance.embeddings[0].values) if appearance.embeddings else 512
            embeddings = np.asarray([vectors[c.candidate_id] for c in candidates], dtype=np.float32).reshape(-1, dimension)
        dets = np.asarray([[c.measurement.bbox.x_min, c.measurement.bbox.y_min,
                           c.measurement.bbox.x_max, c.measurement.bbox.y_max, c.measurement.score, 0]
                          for c in candidates], dtype=np.float32).reshape(-1, 6)
        shape = (frame.source.context.height_px, frame.source.context.width_px, 3)
        if self.image is None or self.image.shape != shape:
            self.image = np.zeros(shape, dtype=np.uint8)
        with self._identity_scope():
            output = self.tracker.update(dets, self.image, embeddings)
        self.previous_timestamp = timestamp
        assignments = {c.candidate_id: -1 for c in candidates}
        for row in output:
            index, tid = int(row[7]), int(row[4])
            if row[7] != index or row[4] != tid or tid < 0 or not 0 <= index < len(candidates):
                raise TrackingError("BoxMOT returned an invalid detection index or ID")
            cid = candidates[index].candidate_id
            if assignments[cid] != -1:
                raise TrackingError("BoxMOT assigned a candidate twice")
            assignments[cid] = tid
            self.known.add(tid)
        alive = []
        # Les llistes públiques poden mantenir un tick de retirada addicional;
        # encara són el pool d'associació de la biblioteca. No es força una
        # finalització anticipada que permetria reaparèixer un ID ja acabat.
        for track in self.tracker.active_tracks + self.tracker.lost_stracks:
            if track.id not in self.known:
                continue
            try:
                box = BoundingBox(*(float(v) for v in track.xyxy))
            except ValueError:
                box = None
            alive.append((int(track.id), box))
        self.known &= {tid for tid, _ in alive}
        return BackendUpdate(tuple(assignments.items()), tuple(alive))

    def describe(self):
        """Declara la implementació i les limitacions temporals efectivament executades."""
        return {"name": self.name, "library": "boxmot", "version": version("boxmot"),
                "nominal_fps": self.nominal_fps, "confirmation_policy": self.config.confirmation_policy,
                "appearance_enabled": self.requires_appearance, "camera_motion": "fixed_identity",
                "lost_buffer_30fps_units": self.config.lost_buffer,
                "retention_semantics": "boxmot_public_lists_may_include_one_retirement_tick",
                "dependencies": {name: version(name) for name in ("boxmot", "torch", "numpy", "scipy")}}
