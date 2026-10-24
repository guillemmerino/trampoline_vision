"""Contractes de preparació i seguiment, independents de la biblioteca de tracking.

El flux és FrameDetections -> TrackingFrame -> TrackingFrameResult. Els tipus
validen geometria, procedència i assignacions d'un instant; no calculen caixes,
no associen persones ni executen transicions temporals. Es preserva la font
original per poder revisar qualsevol decisió sense tornar a executar OpenPose.
"""

from dataclasses import dataclass
import math
from typing import Literal

from trampoline_vision.contracts.observations import FrameDetections


TRACKING_SCHEMA_VERSION = "1.0"  # Versió semàntica dels contractes; encara sense serialitzador públic.


def _finite(value: float, name: str) -> None:
    """Rebutja booleans, valors no numèrics i infinits abans d'usar geometria o temps."""
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")


def _identifier(value: str, name: str) -> None:
    """Exigeix un identificador textual no buit, sense modificar-ne el contingut."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _identifiers(values: tuple[str, ...], name: str) -> None:
    """Valida una col·lecció immutable de referències úniques dins del seu àmbit."""
    if not isinstance(values, tuple):
        raise ValueError(f"{name} must be a tuple")
    for value in values:
        _identifier(value, name)
    if len(set(values)) != len(values):
        raise ValueError(f"Duplicate {name}")


@dataclass(frozen=True)
class BoundingBox:
    """Rectangle xyxy d'àrea positiva en píxels del fotograma original.

    X creix cap a la dreta i Y cap avall; xmax/ymax són límits geomètrics,
    sense sumar un píxel al càlcul de l'àrea. Pot sortir de la imatge: retallar
    és una política de preparació o dibuix, no una mutació del contracte.
    Una caixa de punts visibles no garanteix representar el cos complet.
    """

    x_min: float  # Límit esquerre en píxels, que pot ser negatiu.
    y_min: float  # Límit superior en píxels, que pot ser negatiu.
    x_max: float  # Límit dret estrictament superior a x_min.
    y_max: float  # Límit inferior estrictament superior a y_min.

    def __post_init__(self) -> None:
        """Impedeix caixes degenerades o nombres incompatibles amb l'associació."""
        for name in ("x_min", "y_min", "x_max", "y_max"):
            _finite(getattr(self, name), name)
        if self.x_max <= self.x_min or self.y_max <= self.y_min:
            raise ValueError("Bounding box must have positive width and height")


@dataclass(frozen=True)
class BoxMeasurement:
    """Mesura rectangular que es pot oferir a un tracker basat en caixes.

    score és un indicador entre 0 i 1, amb mètode explícit, no una probabilitat
    calibrada ni una nota esportiva. pose_extent només descriu l'extensió dels
    punts seleccionats. Aquest tipus no calcula ni la caixa ni l'indicador.
    """

    bbox: BoundingBox  # Geometria observada o derivada de la pose, mai una predicció temporal.
    source: Literal["detector", "pose_extent"]  # Distingeix caixa del detector i extensió de punts.
    score: float  # Indicador explícit; zero és vàlid i no s'elimina aquí.
    score_method: str  # Nom i, si escau, versió del càlcul per poder interpretar el valor.

    def __post_init__(self) -> None:
        """Valida origen i indicador sense decidir llindars ni calibrar confiança."""
        if not isinstance(self.bbox, BoundingBox):
            raise ValueError("Measurement requires a BoundingBox")
        if self.source not in ("detector", "pose_extent"):
            raise ValueError("Unknown box measurement source")
        _finite(self.score, "score")
        if not 0 <= self.score <= 1:
            raise ValueError("Score must be within [0, 1]")
        _identifier(self.score_method, "score_method")


@dataclass(frozen=True)
class TrackingCandidate:
    """Hipòtesi preparada d'una persona, amb referències a les deteccions originals.

    Diverses deteccions poden alimentar un candidat si preparation les agrupa.
    Una pose insuficient es conserva amb measurement=None i un motiu explícit;
    no es fabrica una caixa per satisfer l'API externa. La deduplicació i els
    criteris de suficiència s'implementaran a preparation, fora d'aquests tipus.
    """

    candidate_id: str  # ID únic dins del fotograma, encara sense identitat temporal.
    source_detection_ids: tuple[str, ...]  # Una o més observacions del FrameDetections associat.
    measurement: BoxMeasurement | None  # None conserva evidència no convertible en caixa utilitzable.
    issues: tuple[str, ...] = ()  # Motius o limitacions, per exemple insufficient_spatial_support.

    def __post_init__(self) -> None:
        """Exigeix procedència, col·leccions immutables i causa si falta la mesura."""
        _identifier(self.candidate_id, "candidate_id")
        _identifiers(self.source_detection_ids, "source_detection_ids")
        if not self.source_detection_ids:
            raise ValueError("Candidate requires source detections")
        _identifiers(self.issues, "issues")
        if self.measurement is not None and not isinstance(self.measurement, BoxMeasurement):
            raise ValueError("Candidate measurement must be a BoxMeasurement or None")
        if self.measurement is None and not self.issues:
            raise ValueError("Candidate without measurement requires an explicit issue")


@dataclass(frozen=True)
class TrackingFrame:
    """Entrada de tracking: font intacta i candidats preparats del mateix instant.

    El context temporal i source_status continuen a source. Un fotograma buit
    o sense JSON existeix igualment i haurà d'avançar el tracker. Les deteccions
    que no s'han convertit en candidats segueixen accessibles a source.
    """

    source: FrameDetections  # Observacions canòniques amb temps, punts i procedència originals.
    candidates: tuple[TrackingCandidate, ...]  # Resultat immutable de la preparació d'aquest instant.

    def __post_init__(self) -> None:
        """Rebutja referències inexistents i l'ús de la mateixa detecció en dos candidats."""
        if not isinstance(self.source, FrameDetections) or not isinstance(self.candidates, tuple):
            raise ValueError("Tracking frame requires a source and a tuple of candidates")
        if any(not isinstance(c, TrackingCandidate) for c in self.candidates):
            raise ValueError("Invalid tracking candidate")
        _identifiers(tuple(c.candidate_id for c in self.candidates), "candidate IDs")
        available = {d.detection_id for d in self.source.detections}
        used: set[str] = set()
        for candidate in self.candidates:
            refs = set(candidate.source_detection_ids)
            if not refs <= available:
                raise ValueError("Candidate references unknown source detections")
            if refs & used:
                raise ValueError("Source detection used by multiple candidates")
            used.update(refs)


@dataclass(frozen=True)
class TrackSample:
    """Estat d'una identitat en un instant; el context ve del resultat que el conté.

    observed significa que hi ha una mesura associada d'aquest fotograma.
    predicted significa absència de nova mesura: bbox pot ser una estimació o
    None si el backend no n'ofereix. No es creen articulacions ni confiança
    observada a partir d'una predicció. state descriu la vida de la identitat,
    mentre evidence descriu l'origen de la geometria d'aquest instant.
    """

    track_id: str  # Identitat opaca, única dins del vídeo i d'una execució; admet l'ID extern zero.
    state: Literal["tentative", "active", "lost", "finished"]  # Estat de vida decidit pel futur adaptador.
    evidence: Literal["observed", "predicted"]  # Separa mesura actual i hipòtesi sense nova mesura.
    bbox: BoundingBox | None  # Caixa mesurada si observed; estimada o absent si predicted.
    candidate_id: str | None  # Candidat actual assignat; sempre None quan només hi ha predicció.
    last_observed_timestamp_s: float  # Última mesura real en segons de la línia temporal del vídeo.

    def __post_init__(self) -> None:
        """Impedeix estats desconeguts i prediccions que es presentin com a observacions."""
        _identifier(self.track_id, "track_id")
        if self.state not in ("tentative", "active", "lost", "finished"):
            raise ValueError("Unknown track state")
        if self.evidence not in ("observed", "predicted"):
            raise ValueError("Unknown track evidence")
        if self.bbox is not None and not isinstance(self.bbox, BoundingBox):
            raise ValueError("Track bbox must be a BoundingBox or None")
        _finite(self.last_observed_timestamp_s, "last_observed_timestamp_s")
        if self.last_observed_timestamp_s < 0:
            raise ValueError("Last observation time cannot be negative")
        if self.evidence == "observed":
            _identifier(self.candidate_id, "candidate_id")
            if self.bbox is None or self.state in ("lost", "finished"):
                raise ValueError("Observed track requires a box and an observable state")
        elif self.candidate_id is not None:
            raise ValueError("Predicted track cannot claim a current candidate")


@dataclass(frozen=True)
class TrackingFrameResult:
    """Sortida auditable d'un fotograma: identitats i candidats sense assignar.

    Cada candidat és assignat una vegada o figura a unassigned_candidate_ids,
    inclosos els parcials sense caixa. Una trajectòria predita no consumeix cap
    candidat. La seqüència i les transicions entre fotogrames les haurà de
    validar el servei de tracking; aquí només es comprova un instant.
    """

    frame: TrackingFrame  # Entrada exacta de la qual depèn aquest resultat.
    tracks: tuple[TrackSample, ...]  # Mostres amb IDs temporals únics en aquest instant.
    unassigned_candidate_ids: tuple[str, ...]  # Partició explícita de tots els candidats no associats.

    def __post_init__(self) -> None:
        """Valida assignació unívoca, temps d'evidència i coherència amb la caixa mesurada."""
        if not isinstance(self.frame, TrackingFrame) or not isinstance(self.tracks, tuple):
            raise ValueError("Result requires a tracking frame and a tuple of tracks")
        if any(not isinstance(track, TrackSample) for track in self.tracks):
            raise ValueError("Invalid track sample")
        _identifiers(tuple(t.track_id for t in self.tracks), "track IDs")
        _identifiers(self.unassigned_candidate_ids, "unassigned candidate IDs")
        candidates = {c.candidate_id: c for c in self.frame.candidates}
        now = self.frame.source.context.timestamp_s
        assigned: set[str] = set()
        for track in self.tracks:
            if track.evidence == "predicted":
                # L'instant d'una predicció ha de ser posterior a la seva última mesura real.
                if track.last_observed_timestamp_s >= now:
                    raise ValueError("Prediction requires a strictly earlier observation")
                continue
            if track.last_observed_timestamp_s != now:
                raise ValueError("Observed track must use the current frame timestamp")
            candidate = candidates.get(track.candidate_id)
            if candidate is None or candidate.measurement is None:
                raise ValueError("Observed track requires a measured candidate from this frame")
            if track.candidate_id in assigned:
                raise ValueError("Candidate assigned to multiple tracks")
            if track.bbox != candidate.measurement.bbox:
                raise ValueError("Observed box must match its candidate measurement")
            assigned.add(track.candidate_id)
        unassigned = set(self.unassigned_candidate_ids)
        if assigned & unassigned or assigned | unassigned != set(candidates):
            raise ValueError("Assigned and unassigned IDs must partition all candidates")
