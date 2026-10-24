"""Configuració validada del primer backend; els llindars encara no estan calibrats."""

from dataclasses import dataclass, fields
import math

from trampoline_vision.contracts.validation import count_in_range as _count, known_options as _options, number_in_range as _number


@dataclass(frozen=True)
class TrackerConfig:
    """Política d'OC-SORT en unitats explícites, independent del dibuix i de la selecció del gimnasta."""

    backend: str = "ocsort"  # Únic backend registrat; altres noms generen error.
    confidence_threshold: float = 0.1  # Admissió a associació i naixement, sense passada de confiança baixa.
    confirmation_frames: int = 3  # Confirmació gestionada pel backend; -1 no es publica com a identitat.
    max_lost_s: float = 0.5  # Temps des de l'última observació abans d'expirar, arrodonit a unitats d'1/30 s.
    min_iou: float = 0.1  # Solapament mínim per associació; hipòtesi inicial a provar.
    direction_weight: float = 0.2  # Pes de consistència de direcció, sense unitats.
    velocity_lookback_frames: int = 3  # delta_t del backend; no és temps transcorregut.

    def __post_init__(self) -> None:
        """Rebutja opcions incompatibles abans de carregar dependències o processar dades."""
        if self.backend != "ocsort":
            raise ValueError("Only the ocsort backend is implemented")
        _number(self.confidence_threshold, "confidence_threshold", 0, 1)
        _count(self.confirmation_frames, "confirmation_frames", 1, 1000)
        _number(self.max_lost_s, "max_lost_s", 0, 3600)
        _number(self.min_iou, "min_iou", 0, 1)
        _number(self.direction_weight, "direction_weight", 0, 1)
        _count(self.velocity_lookback_frames, "velocity_lookback_frames", 1, 1000)

    @property
    def lost_buffer(self) -> int:
        """Converteix segons a les unitats enteres de 30 FPS de la biblioteca, arrodonint cap amunt."""
        return math.ceil(self.max_lost_s * 30)

    @classmethod
    def from_dict(cls, value: dict) -> "TrackerConfig":
        """Valida opcions conegudes i resol defaults sense consumir configuracions d'altres dominis."""
        return cls(**_options(value, {f.name for f in fields(cls)}, "tracker"))
