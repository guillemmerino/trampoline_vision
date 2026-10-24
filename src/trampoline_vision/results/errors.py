"""Errors esperats de visualització que la CLI presenta sense un traceback intern."""

from trampoline_vision.ingestion.errors import InputError


class VisualizationError(InputError):
    """No es pot dibuixar, codificar o sincronitzar la sortida amb les dades declarades."""
