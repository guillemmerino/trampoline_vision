"""Contractes immutables de traça i fragments, sense reconstruir actors.

La traça conserva mesures, candidats, procedència i prediccions. Un fragment
conté només observacions consecutives; els buits conserven les prediccions
i els estats finished. No es fabriquen poses ni observacions intermèdies.
"""

from dataclasses import dataclass
import math

from trampoline_vision.contracts.observations import DetectionProvenance, FrameContext
from trampoline_vision.contracts.tracking import TrackSample, TrackingCandidate


def identifier(value, name):
    """Exigeix una referència textual no buida, sense conversions implícites."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{name} must be a non-empty string')


@dataclass(frozen=True)
class TraceCandidate:
    """Candidat exportat amb fonts, sense reconstruir la pose absent del JSONL."""

    candidate: TrackingCandidate
    provenance: tuple[DetectionProvenance, ...]
    unassigned_reason: str | None = None

    def __post_init__(self):
        """Comprova correspondència entre referències originals i procedència."""
        if not isinstance(self.candidate, TrackingCandidate) or not isinstance(self.provenance, tuple):
            raise ValueError('Invalid trace candidate')
        if len(self.provenance) != len(self.candidate.source_detection_ids) or any(not isinstance(p, DetectionProvenance) for p in self.provenance):
            raise ValueError('Each source detection requires provenance')
        if self.unassigned_reason is not None:
            identifier(self.unassigned_reason, 'unassigned_reason')
        for source in self.provenance:
            for name in ('source_path', 'source_record', 'variant', 'rotation_provenance'):
                identifier(getattr(source, name), name)
            for name in ('source_frame_index', 'source_person_index'):
                if type(getattr(source, name)) is not int or getattr(source, name) < 0:
                    raise ValueError('Invalid provenance index')


@dataclass(frozen=True)
class TraceEvent:
    """Transició del tracker al mateix fotograma que l'evidència."""

    track_id: str
    kind: str
    timestamp_s: float

    def __post_init__(self):
        """Valida vocabulari i temps; la continuïtat entre frames es valida al lector."""
        identifier(self.track_id, 'track_id')
        if self.kind not in ('confirmed', 'lost', 'recovered', 'finished'):
            raise ValueError('Unknown tracking event')
        if type(self.timestamp_s) not in (int, float) or not math.isfinite(self.timestamp_s) or self.timestamp_s < 0:
            raise ValueError('Invalid event timestamp')


@dataclass(frozen=True)
class TrackingTraceFrame:
    """Instant de traça amb candidats no associats i geometria predita preservats."""

    context: FrameContext
    source_status: str
    source_detections: int
    candidates: tuple[TraceCandidate, ...]
    tracks: tuple[TrackSample, ...]
    unassigned_candidate_ids: tuple[str, ...]
    events: tuple[TraceEvent, ...]

    def __post_init__(self):
        """Valida particions, referències i geometria observada sense fabricar punts."""
        if not isinstance(self.context, FrameContext) or self.source_status not in ('present', 'missing'):
            raise ValueError('Invalid trace context/status')
        if type(self.source_detections) is not int or self.source_detections < 0:
            raise ValueError('Invalid source detection count')
        for values, expected in ((self.candidates, TraceCandidate), (self.tracks, TrackSample), (self.events, TraceEvent)):
            if not isinstance(values, tuple) or any(not isinstance(v, expected) for v in values):
                raise ValueError('Trace collections must be typed tuples')
        if not isinstance(self.unassigned_candidate_ids, tuple):
            raise ValueError('Unassigned references must be a tuple')
        for cid in self.unassigned_candidate_ids:
            identifier(cid, 'candidate_id')
        candidates = {c.candidate.candidate_id: c for c in self.candidates}
        source_ids = [sid for c in self.candidates for sid in c.candidate.source_detection_ids]
        if len(candidates) != len(self.candidates) or len(set(source_ids)) != len(source_ids) or len(source_ids) > self.source_detections:
            raise ValueError('Repeated candidates/source references or inconsistent count')
        if self.source_status == 'missing' and (self.source_detections or self.candidates):
            raise ValueError('Missing source cannot contain detections')
        if len({s.track_id for s in self.tracks}) != len(self.tracks):
            raise ValueError('Repeated track ID in frame')
        assigned = []
        for sample in self.tracks:
            if sample.state == 'tentative' or (sample.state == 'active') != (sample.evidence == 'observed'):
                raise ValueError('Public track state and evidence disagree')
            if sample.evidence == 'observed':
                candidate = candidates.get(sample.candidate_id)
                if candidate is None or candidate.candidate.measurement is None:
                    raise ValueError('Observed track requires a measured candidate')
                if candidate.unassigned_reason is not None:
                    raise ValueError('Assigned candidate cannot declare an unassigned reason')
                if sample.bbox != candidate.candidate.measurement.bbox or sample.last_observed_timestamp_s != self.context.timestamp_s:
                    raise ValueError('Observed geometry or timestamp differs from measurement')
                assigned.append(sample.candidate_id)
            elif sample.last_observed_timestamp_s >= self.context.timestamp_s:
                raise ValueError('Prediction must refer to an earlier observation')
            if sample.state == 'finished' and sample.bbox is not None:
                raise ValueError('Finished track cannot carry a box')
        unassigned = self.unassigned_candidate_ids
        if len(set(assigned)) != len(assigned) or len(set(unassigned)) != len(unassigned) or set(assigned) & set(unassigned) or set(assigned) | set(unassigned) != set(candidates):
            raise ValueError('Assigned and unassigned candidates must form an exclusive partition')
        if any(event.timestamp_s != self.context.timestamp_s for event in self.events) or len({(e.track_id, e.kind) for e in self.events}) != len(self.events):
            raise ValueError('Repeated event or invalid event timestamp')


@dataclass(frozen=True)
class TrackingTrace:
    """Traça d'un únic vídeo/run; la cobertura externa la contrasta ingestion amb el vídeo."""

    video_id: str
    run_id: str
    frames: tuple[TrackingTraceFrame, ...]

    def __post_init__(self):
        """Impedeix salts d'índex interns, vídeos barrejats i dimensions variables."""
        identifier(self.video_id, 'video_id')
        identifier(self.run_id, 'run_id')
        if not isinstance(self.frames, tuple) or not self.frames or any(not isinstance(f, TrackingTraceFrame) for f in self.frames):
            raise ValueError('Trace requires typed non-empty frames')
        previous = None
        for index, frame in enumerate(self.frames):
            ctx = frame.context
            if ctx.video_id != self.video_id or ctx.frame_index != index or index == 0 and ctx.timestamp_s != 0:
                raise ValueError('Trace must start at zero with consecutive frames of one video')
            if previous and (ctx.timestamp_s <= previous.timestamp_s or (ctx.width_px, ctx.height_px) != (previous.width_px, previous.height_px) or not math.isclose(previous.timestamp_s + previous.duration_s, ctx.timestamp_s, rel_tol=0, abs_tol=1e-6)):
                raise ValueError('Trace timing or geometry is inconsistent')
            previous = ctx


@dataclass(frozen=True)
class TrajectorySample:
    """Mostra de track amb context i candidat real només si és observada."""

    context: FrameContext
    track: TrackSample
    candidate: TraceCandidate | None

    def __post_init__(self):
        """Manté inseparables l'evidència i les referències d'auditoria."""
        if not isinstance(self.context, FrameContext) or not isinstance(self.track, TrackSample):
            raise ValueError('Trajectory sample requires context and track')
        if self.track.evidence == 'observed':
            if not isinstance(self.candidate, TraceCandidate) or self.track.candidate_id != self.candidate.candidate.candidate_id or self.candidate.candidate.measurement is None:
                raise ValueError('Observation requires its measured source candidate')
            if self.track.bbox != self.candidate.candidate.measurement.bbox or self.track.last_observed_timestamp_s != self.context.timestamp_s:
                raise ValueError('Observation differs from source measurement')
        elif self.candidate is not None or self.track.last_observed_timestamp_s >= self.context.timestamp_s:
            raise ValueError('Prediction cannot claim a current candidate')


@dataclass(frozen=True)
class TrajectoryFragment:
    """Ratxa de mesures consecutives d'un track segons la política inicial."""

    fragment_id: str
    track_id: str
    samples: tuple[TrajectorySample, ...]
    start_reason: str
    end_reason: str

    def __post_init__(self):
        """Exigeix observacions contigües i motius explícits dels límits."""
        identifier(self.fragment_id, 'fragment_id')
        identifier(self.track_id, 'track_id')
        if self.start_reason not in ('confirmed', 'recovered') or self.end_reason not in ('lost', 'finished', 'video_end'):
            raise ValueError('Invalid fragment boundary')
        if not isinstance(self.samples, tuple) or not self.samples or any(not isinstance(s, TrajectorySample) or s.track.track_id != self.track_id or s.track.evidence != 'observed' for s in self.samples):
            raise ValueError('Fragments require observed samples of one track')
        for a, b in zip(self.samples, self.samples[1:]):
            if b.context.frame_index != a.context.frame_index + 1 or b.context.timestamp_s <= a.context.timestamp_s or b.context.video_id != a.context.video_id:
                raise ValueError('Fragment observations must be consecutive')


@dataclass(frozen=True)
class TrajectoryGap:
    """Evidència predita entre fragments o després de l'última observació d'un track."""

    gap_id: str
    track_id: str
    previous_fragment_id: str
    next_fragment_id: str | None
    samples: tuple[TrajectorySample, ...]
    end_reason: str

    def __post_init__(self):
        """Conserva finished sense comptar-lo com una caixa observada."""
        for value in (self.gap_id, self.track_id, self.previous_fragment_id):
            identifier(value, 'gap reference')
        if self.next_fragment_id is not None:
            identifier(self.next_fragment_id, 'next_fragment_id')
        if self.end_reason not in ('recovered', 'finished', 'video_end') or (self.end_reason == 'recovered') != (self.next_fragment_id is not None):
            raise ValueError('Invalid gap boundary')
        if not isinstance(self.samples, tuple) or not self.samples or any(not isinstance(s, TrajectorySample) or s.track.track_id != self.track_id or s.track.evidence != 'predicted' for s in self.samples):
            raise ValueError('Gap requires predicted samples of one track')
        for a, b in zip(self.samples, self.samples[1:]):
            if b.context.frame_index != a.context.frame_index + 1 or b.context.timestamp_s <= a.context.timestamp_s or b.context.video_id != a.context.video_id or a.track.state == 'finished':
                raise ValueError('Gap samples must be consecutive and cannot follow finished')
        if (self.end_reason == 'finished') != (self.samples[-1].track.state == 'finished'):
            raise ValueError('Gap termination differs from tracker evidence')


@dataclass(frozen=True)
class FragmentLink:
    """Evidència de proposta experimental, sense aplicar unions al tracking.

Els costos són evidències, no probabilitats calibrades. La compatibilitat
    temporal i de cadena es valida al pipeline; això no certifica identitat.
    A audit, proposed significa escollit pel solver i pendent de revisió.
"""

    source_fragment_id: str
    target_fragment_id: str
    status: str
    costs: tuple[tuple[str, float], ...] = ()
    reasons: tuple[str, ...] = ()

    def __post_init__(self):
        """Impedeix autoenllaços, estats inventats i costos no finits."""
        identifier(self.source_fragment_id, 'source_fragment_id')
        identifier(self.target_fragment_id, 'target_fragment_id')
        if self.source_fragment_id == self.target_fragment_id or self.status not in ('proposed', 'accepted', 'rejected', 'pending'):
            raise ValueError('Invalid fragment link')
        if not isinstance(self.costs, tuple) or not isinstance(self.reasons, tuple):
            raise ValueError('Link evidence must be immutable')
        names = []
        for name, value in self.costs:
            identifier(name, 'cost name')
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError('Link costs must be finite')
            names.append(name)
        if len(set(names)) != len(names):
            raise ValueError('Repeated link cost')
        for reason in self.reasons:
            identifier(reason, 'reason')


@dataclass(frozen=True)
class FragmentationResult:
    """Preparació de recovery; encara no assigna actor_id ni aplica unions."""

    trace: TrackingTrace
    policy: str
    fragments: tuple[TrajectoryFragment, ...]
    gaps: tuple[TrajectoryGap, ...]

    def __post_init__(self):
        """Exigeix resultats tipats; la partició i els enllaços es validen a recovery.validation."""
        if not isinstance(self.trace, TrackingTrace) or self.policy != 'consecutive_observations_v1':
            raise ValueError('Invalid fragmentation source or policy')
        for values, expected in ((self.fragments, TrajectoryFragment), (self.gaps, TrajectoryGap)):
            if not isinstance(values, tuple) or any(not isinstance(v, expected) for v in values):
                raise ValueError('Fragmentation blocks must be typed tuples')
