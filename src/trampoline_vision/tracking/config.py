"""Perfils de tracking estrictes: vida comuna i paràmetres propis de cada adaptador.

El constructor conserva les opcions OC-SORT 0.4.0 per compatibilitat Python.
Els perfils 2.0 separen lifecycle, parameters i appearance i rebutgen opcions
que un altre tracker ignoraria. Llegir configuració no carrega cap model.
"""

from dataclasses import dataclass
import math

from trampoline_vision.contracts.validation import count_in_range as _count, known_options as _options, number_in_range as _number
from trampoline_vision.perception.appearance.config import AppearanceConfig


@dataclass(frozen=True)
class OCSortParameters:
    """Opcions pròpies d'OC-SORT, sense barrejar-les amb naixement o expiració."""

    min_iou: float = .1
    direction_weight: float = .2
    velocity_lookback_frames: int = 3

    def __post_init__(self) -> None:
        """Valida geometria, pes de direcció i finestra d'observacions."""
        _number(self.min_iou, "min_iou", 0, 1)
        _number(self.direction_weight, "direction_weight", 0, 1)
        _count(self.velocity_lookback_frames, "velocity_lookback_frames", 1, 1000)


@dataclass(frozen=True)
class ByteTrackParameters:
    """Admissió baixa i geometria de ByteTrack; la confiança forta és comuna."""

    min_iou: float = .1
    low_confidence: float = .02

    def __post_init__(self) -> None:
        """Rebutja llindars fora del rang abans de carregar la biblioteca."""
        _number(self.min_iou, "min_iou", 0, 1)
        _number(self.low_confidence, "low_confidence", 0, 1)


@dataclass(frozen=True)
class BotSortParameters:
    """Distàncies d'associació BoT-SORT; aparença i pesos són una configuració separada."""

    low_confidence: float = .02
    match_thresh: float = .9
    proximity_thresh: float = .9
    appearance_thresh: float = .25
    fuse_first_associate: bool = False

    def __post_init__(self) -> None:
        """Valida distàncies i fusió explícita sense equiparar distància a IoU."""
        for name in ("low_confidence", "match_thresh", "proximity_thresh", "appearance_thresh"):
            _number(getattr(self, name), name, 0, 1)
        if type(self.fuse_first_associate) is not bool:
            raise ValueError("fuse_first_associate must be boolean")


PARAMETERS = {"ocsort": OCSortParameters, "bytetrack": ByteTrackParameters, "botsort": BotSortParameters}


@dataclass(frozen=True, init=False)
class TrackerConfig:
    """Configuració resolta i immutable, independent del lector i de la biblioteca externa."""

    backend: str
    confirmation_policy: str
    confidence_threshold: float
    confirmation_frames: int
    max_lost_s: float
    parameters: OCSortParameters | ByteTrackParameters | BotSortParameters
    appearance: AppearanceConfig | None

    def __init__(self, backend="ocsort", confirmation_policy="birth_streak_v1", confidence_threshold=.1,
                 confirmation_frames=3, max_lost_s=.5, *, parameters=None, appearance=None,
                 min_iou=None, direction_weight=None, velocity_lookback_frames=None):
        """Construeix un perfil resolt i admet els arguments OC-SORT anteriors sense ignorar-los."""
        if not isinstance(backend, str) or backend not in PARAMETERS:
            raise ValueError("Unknown tracking backend; choose ocsort, bytetrack or botsort")
        legacy = {key: value for key, value in {"min_iou": min_iou, "direction_weight": direction_weight,
                  "velocity_lookback_frames": velocity_lookback_frames}.items() if value is not None}
        if legacy and (backend != "ocsort" or parameters is not None):
            raise ValueError("Legacy OC-SORT options cannot be mixed with another backend or parameters")
        params = PARAMETERS[backend](**legacy) if parameters is None else parameters
        if not isinstance(params, PARAMETERS[backend]):
            raise ValueError("Parameters do not belong to selected backend")
        if confirmation_policy != "birth_streak_v1":
            raise ValueError("Only birth_streak_v1 confirmation is implemented")
        _number(confidence_threshold, "confidence_threshold", 0, 1)
        _count(confirmation_frames, "confirmation_frames", 1, 1000)
        _number(max_lost_s, "max_lost_s", 0, 3600)
        if backend != "ocsort" and params.low_confidence >= confidence_threshold:
            raise ValueError("low_confidence must be below the strong confidence_threshold")
        if appearance is not None and (not isinstance(appearance, AppearanceConfig) or backend != "botsort"):
            raise ValueError("Appearance is supported only by botsort")
        for key, value in {"backend": backend, "confirmation_policy": confirmation_policy,
                           "confidence_threshold": confidence_threshold, "confirmation_frames": confirmation_frames,
                           "max_lost_s": max_lost_s, "parameters": params, "appearance": appearance}.items():
            object.__setattr__(self, key, value)

    @property
    def min_iou(self):
        """Compatibilitat de lectura amb els clients OC-SORT 0.4.0."""
        return self.parameters.min_iou

    @property
    def direction_weight(self):
        """Exposa el pes exclusiu d'OC-SORT per als clients Python anteriors."""
        return self.parameters.direction_weight

    @property
    def velocity_lookback_frames(self):
        """Exposa la finestra exclusiva d'OC-SORT per compatibilitat."""
        return self.parameters.velocity_lookback_frames

    @property
    def lost_buffer(self) -> int:
        """Converteix el pressupost nominal a unitats de 30 FPS que els adaptadors tradueixen."""
        return math.ceil(self.max_lost_s * 30)

    @classmethod
    def from_dict(cls, value: dict) -> "TrackerConfig":
        """Valida un perfil 2.0 resolt o el bloc inline OC-SORT 1.0 anterior."""
        if not isinstance(value, dict):
            raise ValueError("tracker must be an object")
        if value.get("schema_version") == "2.0" or "lifecycle" in value or "parameters" in value or "appearance" in value:
            _options(value, {"schema_version", "backend", "lifecycle", "parameters", "appearance"}, "tracker profile")
            if value.get("schema_version", "2.0") != "2.0":
                raise ValueError("Tracker profile schema_version must be 2.0")
            backend = value.get("backend", "ocsort")
            if not isinstance(backend, str) or backend not in PARAMETERS:
                raise ValueError("Unknown tracking backend")
            lifecycle = _options(value.get("lifecycle", {}), {"confirmation_policy", "confidence_threshold", "confirmation_frames", "max_lost_s"}, "lifecycle")
            fields = PARAMETERS[backend].__dataclass_fields__
            parameters = PARAMETERS[backend](**_options(value.get("parameters", {}), set(fields), backend))
            appearance = value.get("appearance")
            if isinstance(appearance, dict):
                appearance = AppearanceConfig(**_options(appearance, set(AppearanceConfig.__dataclass_fields__), "appearance"))
            return cls(backend=backend, parameters=parameters, appearance=appearance, **lifecycle)
        return cls(**_options(value, {"backend", "confirmation_policy", "confidence_threshold", "confirmation_frames",
                   "max_lost_s", "min_iou", "direction_weight", "velocity_lookback_frames"}, "tracker"))
