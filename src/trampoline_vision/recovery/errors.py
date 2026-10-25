"""Errors de configuració, lectura i preparació de la reconstrucció."""

from trampoline_vision.ingestion.errors import InputError


class RecoveryError(InputError):
    """Una entrada incoherent impedeix publicar fragments com si fossin vàlids."""
