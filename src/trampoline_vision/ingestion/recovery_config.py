"""Lectura del perfil de diagnòstic sense alterar el pipeline de tracking."""

from trampoline_vision.ingestion.errors import InputError
from trampoline_vision.ingestion.json_io import read_json
from trampoline_vision.recovery.config import FragmentationConfig
from trampoline_vision.recovery.errors import RecoveryError


def load_fragmentation_config(path):
    """Converteix el JSON executable o comunica perquè un perfil draft no ho és."""
    try:
        return FragmentationConfig.from_dict(read_json(path))
    except (InputError, ValueError, TypeError) as exc:
        raise RecoveryError(f'Invalid fragmentation configuration {path}: {exc}') from exc
