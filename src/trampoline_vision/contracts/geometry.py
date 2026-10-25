"""Geometria comuna de detecció i tracking, independent de models i biblioteques."""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class BoundingBox:
    """Rectangle xyxy finit d'àrea positiva, en píxels del fotograma original.

    Les prediccions poden sortir del vídeo. Validar límits d'una detecció
    correspon al lector; retallar per dibuixar no canvia aquesta mesura.
    """

    x_min: float  # Límit esquerre.
    y_min: float  # Límit superior.
    x_max: float  # Límit dret, sense sumar un píxel a l'àrea.
    y_max: float  # Límit inferior.

    def __post_init__(self) -> None:
        """Rebutja geometria degenerada, booleans i coordenades no finites."""
        for value in (self.x_min, self.y_min, self.x_max, self.y_max):
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError("Bounding box coordinates must be finite numbers")
        if self.x_max <= self.x_min or self.y_max <= self.y_min:
            raise ValueError("Bounding box must have positive width and height")
