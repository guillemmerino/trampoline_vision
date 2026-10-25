"""Preparació offline després del tracking; encara no resol enllaços entre fragments."""

from trampoline_vision.recovery.config import FragmentationConfig
from trampoline_vision.recovery.errors import RecoveryError
from trampoline_vision.recovery.tracklets import build_fragments
from trampoline_vision.recovery.validation import validate_fragmentation, validate_lifecycle


def prepare_recovery(trace, config=FragmentationConfig()):
    """Construeix fragments i comprova que cap mostra es perd, duplica o reescriu."""
    try:
        validate_lifecycle(trace)
    except ValueError as exc:
        raise RecoveryError(f'Cannot prepare inconsistent tracking: {exc}') from exc
    result = build_fragments(trace, config)
    validate_fragmentation(result, enabled=config.enabled)
    return result
