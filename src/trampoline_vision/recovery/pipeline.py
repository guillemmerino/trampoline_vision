"""Preparació offline i propostes experimentals després del tracking immutable."""

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


def audit_recovery(trace, config, appearances=None):
    """Genera hipòtesis auditables sense reemplaçar IDs ni mostres de la traça."""
    from trampoline_vision.recovery.association import associate
    from trampoline_vision.recovery.coherence import diagnostics
    from trampoline_vision.recovery.features import describe_fragments
    from trampoline_vision.recovery.config import RecoveryAuditConfig
    from trampoline_vision.recovery.validation import build_validated_chains
    if not isinstance(config, RecoveryAuditConfig):
        raise RecoveryError('Expected explicit experimental audit config')
    prepared=prepare_recovery(trace)
    review=diagnostics(prepared,config.parameters.duplicate_iou)
    if config.strategy=='disabled':
        return prepared,(),(),{'association_executed':False,'review':review}
    if config.strategy=='geometry_appearance' and appearances is None:
        raise RecoveryError('Appearance strategy requires an existing verified descriptor cache')
    features=describe_fragments(prepared,appearances if config.strategy=='geometry_appearance' else None)
    proposals,links,details=associate(features,config)
    chains=build_validated_chains(prepared.fragments,links)
    return prepared,proposals,chains,{**details,'association_executed':True,'review':review}
