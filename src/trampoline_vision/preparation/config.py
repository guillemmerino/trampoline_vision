"""Polítiques immutables de preparació, sense llegir fitxers ni carregar models.

Els valors inicials són hipòtesis explícites, no llindars calibrats sobre el
vídeo de referència. from_dict permet consumir JSON ja llegit per ingestion;
dataclasses.asdict retorna la configuració efectiva amb tots els defaults.
"""

from dataclasses import dataclass, fields
from trampoline_vision.contracts.validation import count_in_range as _count, known_options as _options, number_in_range as _number


@dataclass(frozen=True)
class PoseBoxPolicy:
    """Criteris per construir una extensió rectangular de punts, sense completar anatomia absent."""

    min_keypoint_confidence: float = 0.0  # S'admet qualsevol confiança positiva per defecte.
    min_points: int = 4  # Recompte mínim de punts utilitzables; no és el filtre visual.
    min_anatomical_groups: int = 2  # Grups diferents entre head, core, arms i legs.
    require_core: bool = True  # Exigeix coll, espatlla, maluc o mid_hip com a ancoratge.
    min_span_px: float = 1.0  # Amplada i alçada mínimes abans de padding, en píxels.
    min_span_image_ratio: float = 0.002  # Mínim addicional respecte de la diagonal de la imatge.
    padding_ratio: float = 0.05  # Marge per costat com a fracció de l'amplada/alçada observades.

    def __post_init__(self) -> None:
        """Valida opcions geomètriques i de suport sense introduir una puntuació esportiva."""
        _number(self.min_keypoint_confidence, "min_keypoint_confidence", 0, 1)
        _count(self.min_points, "min_points", 2, 25)
        _count(self.min_anatomical_groups, "min_anatomical_groups", 1, 4)
        if type(self.require_core) is not bool:
            raise ValueError("require_core must be boolean")
        _number(self.min_span_px, "min_span_px", 0, 1_000_000)
        _number(self.min_span_image_ratio, "min_span_image_ratio", 0, 1)
        _number(self.padding_ratio, "padding_ratio", 0, 1)


@dataclass(frozen=True)
class DeduplicationPolicy:
    """Comparació conservadora de caixes i punts homòlegs, desactivada fins a calibrar-la."""

    enabled: bool = False  # Activació expressa; conservar tot és el baseline inicial.
    min_box_iou: float = 0.7  # Solapament mínim de les extensions sense padding.
    min_shared_points: int = 4  # Punts homòlegs seleccionats presents a totes dues poses.
    max_point_distance_ratio: float = 0.08  # Distància màxima de cada punt / menor diagonal de pose.

    def __post_init__(self) -> None:
        """Valida llindars; una tolerància zero permet exigir coincidència exacta dels punts."""
        if type(self.enabled) is not bool:
            raise ValueError("enabled must be boolean")
        _number(self.min_box_iou, "min_box_iou", 0, 1)
        _count(self.min_shared_points, "min_shared_points", 2, 25)
        _number(self.max_point_distance_ratio, "max_point_distance_ratio", 0, 1)


@dataclass(frozen=True)
class PreparationConfig:
    """Configuració completa de l'operació FrameDetections -> TrackingFrame, versió 1.0."""

    box: PoseBoxPolicy = PoseBoxPolicy()  # Política independent de RenderStyle i del tracker.
    deduplication: DeduplicationPolicy = DeduplicationPolicy()  # Cap associació entre instants.

    def __post_init__(self) -> None:
        """Impedeix injectar diccionaris sense validar als preparadors."""
        if not isinstance(self.box, PoseBoxPolicy) or not isinstance(self.deduplication, DeduplicationPolicy):
            raise ValueError("PreparationConfig requires validated policies")

    @classmethod
    def from_dict(cls, value: dict) -> "PreparationConfig":
        """Valida un objecte JSON 1.0, rebutja claus desconegudes i resol opcions omeses.

        No llegeix disc. El caller pot usar ingestion.json_io.read_json per
        rebutjar també claus JSON duplicades abans d'arribar a aquest mètode.
        """
        _options(value, {"schema_version", "box", "deduplication"}, "preparation")
        if value.get("schema_version") != "1.0":
            raise ValueError("Preparation config requires schema_version 1.0")
        box = _options(value.get("box", {}), {f.name for f in fields(PoseBoxPolicy)}, "box")
        dedup = _options(value.get("deduplication", {}), {f.name for f in fields(DeduplicationPolicy)}, "deduplication")
        return cls(PoseBoxPolicy(**box), DeduplicationPolicy(**dedup))
