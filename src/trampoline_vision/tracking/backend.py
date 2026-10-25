"""Port comú de tracking: cap import de NumPy, PyTorch ni un model concret.

BackendUpdate conserva assignacions i vida externa; TrackingSession en
valida la semàntica. L'àlies OC-SORT antic es resol mandrosament per
compatibilitat, mentre el flux nou construeix adaptadors amb factory.
"""

from dataclasses import dataclass
from typing import Protocol
from trampoline_vision.contracts.tracking import BoundingBox, TrackingFrame
from trampoline_vision.contracts.appearance import FrameAppearance


@dataclass(frozen=True)
class BackendUpdate:
    """Resposta independent de la biblioteca: una assignació per candidat mesurat i IDs vius."""

    assignments: tuple[tuple[str, int], ...]  # -1 significa encara no associat a un ID extern públic.
    alive: tuple[tuple[int, BoundingBox | None], ...]  # Geometria estimada opcional, sense punts inventats.


class TrackingBackend(Protocol):
    """Interfície que permet canviar d'algoritme sense canviar el registre d'identitats."""

    name: str
    requires_appearance: bool

    def update(self, frame: TrackingFrame, appearance: FrameAppearance | None = None) -> BackendUpdate:
        """Associa candidats d'un instant; els descriptors es referencien per candidate_id."""
        ...

    def describe(self) -> dict:
        """Retorna implementació, versions i semàntica temporal efectives."""
        ...


def __getattr__(name):
    """Conserva l'import Python anterior d'OCSortBackend sense acoblar el port a una biblioteca."""
    if name == "OCSortBackend":
        from trampoline_vision.tracking.backends.ocsort import OCSortBackend
        return OCSortBackend
    raise AttributeError(name)
