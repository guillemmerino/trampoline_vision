"""Registre explícit de backends: seleccionar un perfil no importa els altres adaptadors."""

from trampoline_vision.tracking.config import TrackerConfig


def create_backend(config: TrackerConfig, nominal_fps: float):
    """Construeix només la implementació seleccionada, després de validar-ne la configuració."""
    if config.backend == "ocsort":
        from trampoline_vision.tracking.backends.ocsort import OCSortBackend
        return OCSortBackend(config, nominal_fps)
    if config.backend == "bytetrack":
        from trampoline_vision.tracking.backends.bytetrack import ByteTrackBackend
        return ByteTrackBackend(config, nominal_fps)
    if config.backend == "botsort":
        from trampoline_vision.tracking.backends.botsort import BotSortBackend
        return BotSortBackend(config, nominal_fps)
    raise ValueError("Unknown tracking backend")
