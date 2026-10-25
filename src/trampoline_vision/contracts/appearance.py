"""Descriptors d'aparença associats a candidats locals, sense identitats ni articulacions."""

from dataclasses import dataclass
import math

from trampoline_vision.contracts.observations import FrameContext


@dataclass(frozen=True)
class CandidateEmbedding:
    """Vector normalitzat d'un candidat; el seu índex de fila mai és una identitat."""

    candidate_id: str  # Referència exacta al candidat del mateix fotograma.
    values: tuple[float, ...]  # Descriptor immutable, sense dependència de NumPy al contracte.

    def __post_init__(self) -> None:
        """Exigeix un vector no buit, finit i normalitzat amb tolerància de representació."""
        if not isinstance(self.candidate_id, str) or not self.candidate_id.strip():
            raise ValueError("Embedding requires a candidate ID")
        if not isinstance(self.values, tuple) or not self.values:
            raise ValueError("Embedding values must be a non-empty tuple")
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in self.values):
            raise ValueError("Embedding values must be finite numbers")
        if not math.isclose(sum(v*v for v in self.values), 1, abs_tol=.002):
            raise ValueError("Embedding must be normalized")


@dataclass(frozen=True)
class FrameAppearance:
    """Aparença d'un instant amb procedència del model i descriptors referenciats per candidat."""

    context: FrameContext  # Mateix vídeo, fotograma, PTS i dimensions que l'entrada de tracking.
    model_fingerprint: str  # Pesos i preprocessament que han produït els vectors.
    embeddings: tuple[CandidateEmbedding, ...]  # Una entrada per candidat mesurat, inclosos els febles.

    def __post_init__(self) -> None:
        """Impedeix descriptors barrejats, IDs duplicats o dimensions incompatibles."""
        if not isinstance(self.context, FrameContext) or not isinstance(self.model_fingerprint, str) or not self.model_fingerprint.strip():
            raise ValueError("Appearance requires context and model fingerprint")
        if not isinstance(self.embeddings, tuple) or any(not isinstance(e, CandidateEmbedding) for e in self.embeddings):
            raise ValueError("Invalid appearance entries")
        ids = [e.candidate_id for e in self.embeddings]
        if len(ids) != len(set(ids)) or len({len(e.values) for e in self.embeddings}) > 1:
            raise ValueError("Appearance IDs or dimensions disagree")
