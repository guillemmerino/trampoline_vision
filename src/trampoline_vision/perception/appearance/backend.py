"""Port d'extracció d'aparença: no coneix IDs temporals ni decideix associacions."""

from typing import Protocol
from trampoline_vision.contracts.appearance import FrameAppearance
from trampoline_vision.contracts.tracking import TrackingFrame


class AppearanceExtractor(Protocol):
    """Component substituïble que produeix descriptors per candidat del mateix instant."""

    fingerprint: str

    def extract(self, frame: TrackingFrame, image) -> FrameAppearance:
        """Extreu aparença de píxels BGR originals; mai utilitza una imatge amb overlays."""
        ...

    def describe(self) -> dict:
        """Declara pesos, preprocessament i runtime necessaris per validar un cache."""
        ...
