"""Errors accionables del backend, configuració i seqüències de seguiment."""

from trampoline_vision.ingestion.errors import InputError


class TrackingError(InputError):
    """Impedeix publicar un resultat si manca una capacitat o falla la coherència temporal."""
