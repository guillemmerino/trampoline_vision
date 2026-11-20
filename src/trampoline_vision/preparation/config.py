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
class BoxPreparationPolicy:
    """Preparació de caixes observades, independent de pose, identitat i historial.

    S'activa explícitament: els pipelines existents conserven les seves mesures.
    Els llindars provenen del prototip conservador, no d'una optimització validada.
    La contenció només crea relacions ambigües; no elimina persones ni caixes.
    """

    enabled: bool = False  # Activa agrupament i relacions; False manté una caixa per candidat.
    min_duplicate_iou: float = 0.65  # Solapament estricte per agrupar geometries semblants.
    min_size_similarity: float = 0.80  # Mínim menor/major per amplada i alçada, sense imposar postura.
    max_center_distance_ratio: float = 0.15  # Per eix, respecte de la menor dimensió.
    max_alternative_score_ratio: float = 0.25  # Només agrupar alternatives febles respecte de l'ancoratge.
    min_representative_coverage: float = 0.95  # Representant ha de cobrir aquesta fracció de CADA caixa del grup.
    min_containment_ios: float = 0.95  # Intersecció / àrea petita per proposar una relació.
    min_contained_area_ratio: float = 0.10  # Evita relacionar qualsevol punt de soroll amb tota l'escena.
    max_contained_area_ratio: float = 0.70  # Les caixes de mida semblant tenen un altre criteri.

    def __post_init__(self) -> None:
        """Valida nombres finits, activació explícita i rangs de contenció coherents."""
        if type(self.enabled) is not bool:
            raise ValueError("box_preparation.enabled must be boolean")
        for name in ("min_duplicate_iou", "min_size_similarity", "max_center_distance_ratio",
                     "max_alternative_score_ratio", "min_containment_ios",
                     "min_representative_coverage",
                     "min_contained_area_ratio", "max_contained_area_ratio"):
            _number(getattr(self, name), name, 0, 1)
        if self.min_contained_area_ratio > self.max_contained_area_ratio:
            raise ValueError("Contained area ratio minimum exceeds maximum")


@dataclass(frozen=True)
class RepresentativeBoxPolicy:
    """Perfil explícit de rànquing per silueta sobre una zona calibrada del vídeo."""

    zone: tuple[float, float, float, float]  # Coordenades xyxy normalitzades respecte del fotograma original.
    max_candidates: int = 12
    zone_mode: str = "soft"  # Preferència espacial; "hard" activa un filtre explícit.

    def __post_init__(self) -> None:
        """Valida la zona, el límit de candidates i el tractament de les deteccions exteriors."""
        if not isinstance(self.zone, (tuple, list)) or len(self.zone) != 4:
            raise ValueError("representative_boxes.zone requires four normalized xyxy coordinates")
        for coordinate in self.zone:
            _number(coordinate, "representative_boxes.zone", 0, 1)
        x_min, y_min, x_max, y_max = self.zone
        if x_min >= x_max or y_min >= y_max:
            raise ValueError("representative_boxes.zone must have positive area")
        object.__setattr__(self, "zone", tuple(self.zone))
        _count(self.max_candidates, "representative_boxes.max_candidates", 1, 3000)
        if self.zone_mode not in ("hard", "soft"):
            raise ValueError("representative_boxes.zone_mode must be hard or soft")


@dataclass(frozen=True)
class PreparationConfig:
    """Configuració completa de l'operació FrameDetections -> TrackingFrame, versió 1.0."""

    box: PoseBoxPolicy = PoseBoxPolicy()  # Política independent de RenderStyle i del tracker.
    deduplication: DeduplicationPolicy = DeduplicationPolicy()  # Cap associació entre instants.
    box_preparation: BoxPreparationPolicy = BoxPreparationPolicy()  # Camí independent per deteccions YOLO.
    representative_boxes: RepresentativeBoxPolicy | None = None  # Perfil explícit que consumeix píxels.

    def __post_init__(self) -> None:
        """Impedeix injectar diccionaris sense validar als preparadors."""
        if (not isinstance(self.box, PoseBoxPolicy) or not isinstance(self.deduplication, DeduplicationPolicy)
                or not isinstance(self.box_preparation, BoxPreparationPolicy)):
            raise ValueError("PreparationConfig requires validated policies")
        if self.representative_boxes is not None:
            if not isinstance(self.representative_boxes, RepresentativeBoxPolicy):
                raise ValueError("PreparationConfig requires a validated representative box policy")
            if not self.box_preparation.enabled:
                raise ValueError("Representative box preparation requires box_preparation.enabled")

    @classmethod
    def from_dict(cls, value: dict) -> "PreparationConfig":
        """Valida un objecte JSON 1.0, rebutja claus desconegudes i resol opcions omeses.

        No llegeix disc. El caller pot usar ingestion.json_io.read_json per
        rebutjar també claus JSON duplicades abans d'arribar a aquest mètode.
        """
        _options(value, {"schema_version", "box", "deduplication", "box_preparation", "representative_boxes"}, "preparation")
        if value.get("schema_version") != "1.0":
            raise ValueError("Preparation config requires schema_version 1.0")
        box = _options(value.get("box", {}), {f.name for f in fields(PoseBoxPolicy)}, "box")
        dedup = _options(value.get("deduplication", {}), {f.name for f in fields(DeduplicationPolicy)}, "deduplication")
        boxes = _options(value.get("box_preparation", {}), {f.name for f in fields(BoxPreparationPolicy)}, "box_preparation")
        representative = value.get("representative_boxes")
        if representative is not None:
            _options(representative, {f.name for f in fields(RepresentativeBoxPolicy)}, "representative_boxes")
            if "zone" not in representative:
                raise ValueError("representative_boxes.zone is required")
            representative = RepresentativeBoxPolicy(**representative)
        return cls(PoseBoxPolicy(**box), DeduplicationPolicy(**dedup), BoxPreparationPolicy(**boxes), representative)
