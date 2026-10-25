"""Configuració del model visual d'aparença, sense carregar pesos ni biblioteques."""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class AppearanceConfig:
    """Model preentrenat explícit, dispositiu i cache; les rutes es resolen a ingestion."""

    provider: str  # Nom d'adaptador, actualment osnet.
    weights: str  # Ruta absoluta resolta; mai es descarrega implícitament.
    sha256: str  # Bytes exactes del checkpoint acceptat.
    device: str = "cpu"  # cpu, cuda o cuda:N; la disponibilitat es comprova abans d'inferir.
    cache_dir: str | None = None  # Cache SQLite opcional fora dels inputs.
    threads: int = 4  # Fils CPU fixats al model; es conserven a la identitat del cache.

    def __post_init__(self) -> None:
        """Rebutja proveïdors, hashes o opcions que no es poden executar explícitament."""
        if self.provider != "osnet":
            raise ValueError("Only the osnet appearance provider is implemented")
        if not isinstance(self.weights, str) or not self.weights.strip():
            raise ValueError("Appearance weights must be an explicit path")
        if not isinstance(self.sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", self.sha256):
            raise ValueError("Appearance requires an expected SHA-256")
        if not isinstance(self.device, str) or not re.fullmatch(r"cpu|cuda(?::[0-9]+)?", self.device):
            raise ValueError("Appearance device must be cpu, cuda or cuda:N")
        if self.cache_dir is not None and (not isinstance(self.cache_dir, str) or not self.cache_dir.strip()):
            raise ValueError("Appearance cache_dir must be a path or null")
        if type(self.threads) is not int or not 1 <= self.threads <= 64:
            raise ValueError("Appearance threads must be an integer in [1, 64]")
