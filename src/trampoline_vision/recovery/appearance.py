"""Distància entre descriptors mitjans verificats; no és confiança d'identitat."""

from trampoline_vision.recovery.errors import RecoveryError


def appearance_cost(a,b,scale):
    """Evita comparar vectors absents o incompatibles encara que el solver ho permetés."""
    if a.appearance is None or b.appearance is None or len(a.appearance)!=len(b.appearance):
        raise RecoveryError('Verified appearance is required for this strategy')
    distance=max(0.,min(2.,1-sum(x*y for x,y in zip(a.appearance,b.appearance))))
    return min(1.,distance/scale),distance
