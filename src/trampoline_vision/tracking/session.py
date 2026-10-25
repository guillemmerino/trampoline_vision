"""Seguiment temporal amb registre propi d'identitats i transicions auditables.

El backend decideix associació; la sessió confirma només els naixements. Preserva últimes
observacions i explicita pèrdues, recuperacions i expiracions sense fabricar
articulacions. Una sessió mai es reutilitza per un altre vídeo.
"""

from dataclasses import dataclass
import math

from trampoline_vision.contracts.tracking import TrackSample, TrackingFrame, TrackingFrameResult
from trampoline_vision.tracking.factory import create_backend
from trampoline_vision.contracts.appearance import FrameAppearance
from trampoline_vision.tracking.config import TrackerConfig
from trampoline_vision.tracking.errors import TrackingError


@dataclass(frozen=True)
class TrackEvent:
    """Transició dins del fotograma que conté l'exportació; no és una anotació de veritat terreny."""

    track_id: str  # Identitat del domini, amb prefix del backend.
    kind: str  # confirmed, lost, recovered o finished.
    timestamp_s: float  # Instant en què s'observa la transició, no necessàriament el moment físic d'oclusió.


class TrackingSession:
    """Consumeix tots els fotogrames consecutius, inclosos buits, preservant el temps original."""

    def __init__(self, config: TrackerConfig, nominal_fps: float, *, backend=None):
        """Valida la freqüència de referència i inicialitza un backend i registre nous."""
        if isinstance(nominal_fps, bool) or not isinstance(nominal_fps, (int, float)) or not math.isfinite(nominal_fps) or nominal_fps <= 0:
            raise TrackingError("nominal_fps must be positive and finite")
        self.config = config
        self.backend = backend if backend is not None else create_backend(config, nominal_fps)
        self.appearance_fingerprint = None
        self.previous_context = None
        self.live: dict[int, TrackSample] = {}
        self.pending: dict[int, int] = {}  # ID públic extern -> ratxa de mesures; encara no és identitat confirmada.
        self.finished: set[int] = set()
        self.events: tuple[TrackEvent, ...] = ()
        self.failed = False  # Un backend que ha fallat pot tenir estat parcial: cal crear una sessió nova.

    def update(self, frame: TrackingFrame, appearance: FrameAppearance | None = None) -> TrackingFrameResult:
        """Valida seqüència, executa associació i retorna mostres i partició completa de candidats."""
        if self.failed:
            raise TrackingError("Session failed previously; start a new session")
        context = frame.source.context
        previous = self.previous_context
        if previous is None:
            if context.frame_index != 0 or context.timestamp_s != 0:
                raise TrackingError("Tracking must start at video frame zero; warm up before a selected interval")
        elif (context.video_id != previous.video_id or context.frame_index != previous.frame_index + 1
              or context.timestamp_s <= previous.timestamp_s
              or (context.width_px, context.height_px) != (previous.width_px, previous.height_px)):
            raise TrackingError("Tracking requires consecutive frames, increasing times and a single video geometry")
        required = getattr(self.backend, "requires_appearance", False) is True
        if required:
            if not isinstance(appearance, FrameAppearance) or appearance.context != context:
                raise TrackingError("Selected backend requires appearance from the same frame")
            measured = {c.candidate_id for c in frame.candidates if c.measurement is not None}
            if {e.candidate_id for e in appearance.embeddings} != measured:
                raise TrackingError("Appearance does not cover measured candidates exactly")
            if self.appearance_fingerprint is not None and self.appearance_fingerprint != appearance.model_fingerprint:
                raise TrackingError("Appearance model changed during the tracking session")
        elif appearance is not None:
            raise TrackingError("Selected backend does not consume appearance")
        try:
            result = self._update(frame, appearance)
        except Exception:
            self.failed = True
            raise
        self.previous_context = context
        if appearance is not None:
            self.appearance_fingerprint = appearance.model_fingerprint
        return result

    def _update(self, frame: TrackingFrame, appearance: FrameAppearance | None = None) -> TrackingFrameResult:
        """Reconcilia la resposta pública del backend amb evidència actual i identitats anteriors."""
        response = self.backend.update(frame) if appearance is None else self.backend.update(frame, appearance)
        candidates = {c.candidate_id: c for c in frame.candidates}
        measured = {cid for cid, c in candidates.items() if c.measurement is not None}
        assignment_ids = [cid for cid, _ in response.assignments]
        if len(set(assignment_ids)) != len(assignment_ids) or set(assignment_ids) != measured:
            raise TrackingError("Backend assignments do not cover measured candidates exactly once")
        associated = {tid: cid for cid, tid in response.assignments if tid >= 0}
        valid_ids = [tid for _, tid in response.assignments if tid >= 0]
        alive = dict(response.alive)
        if (len(associated) != len(valid_ids) or len(alive) != len(response.alive)
                or any(tid < -1 for _, tid in response.assignments) or any(tid < 0 for tid in alive)
                or not set(associated) <= set(alive) or set(alive) & self.finished):
            raise TrackingError("Backend returned invalid, repeated or reused track identities")
        now = frame.source.context.timestamp_s
        samples, events = [], []
        next_live = {}
        next_pending = {}
        assigned = {}  # Només les associacions d'identitats confirmades consumeixen candidats de sortida.
        for tid in sorted(alive):
            track_id = f"{self.config.backend}:{tid}"
            before = self.live.get(tid)
            if before is None:
                if tid not in associated and tid not in self.pending:
                    raise TrackingError("Backend exposed a new identity without a current observation")
                # Un miss interromp la ratxa de naixement; no comptem la primera
                # detecció -1 perquè encara no tenim una identitat externa auditable.
                strong = tid in associated and candidates[associated[tid]].measurement.score >= self.config.confidence_threshold
                streak = self.pending.get(tid, 0) + 1 if strong else 0
                if streak < self.config.confirmation_frames:
                    next_pending[tid] = streak
                    continue
            if tid in associated:
                cid = associated[tid]
                assigned[tid] = cid
                sample = TrackSample(track_id, "active", "observed", candidates[cid].measurement.bbox, cid, now)
                if before is None:
                    events.append(TrackEvent(track_id, "confirmed", now))
                elif before.state == "lost":
                    events.append(TrackEvent(track_id, "recovered", now))
            else:
                if before is None:
                    raise TrackingError("Backend exposed a new identity without a current observation")
                sample = TrackSample(track_id, "lost", "predicted", alive[tid], None, before.last_observed_timestamp_s)
                if before.state != "lost":
                    events.append(TrackEvent(track_id, "lost", now))
            next_live[tid] = sample
            samples.append(sample)
        for tid in sorted(set(self.live) - set(alive)):
            before = self.live[tid]
            samples.append(TrackSample(before.track_id, "finished", "predicted", None, None, before.last_observed_timestamp_s))
            events.append(TrackEvent(before.track_id, "finished", now))
            self.finished.add(tid)
        # Els pendents que expiren no emeten finalització pública, però el seu
        # ID extern queda retirat igualment per impedir-ne una reutilització.
        self.finished.update(set(self.pending) - set(alive))
        unassigned = tuple(cid for cid in candidates if cid not in set(assigned.values()))
        result = TrackingFrameResult(frame, tuple(samples), unassigned)
        self.live, self.pending, self.events = next_live, next_pending, tuple(events)
        return result
