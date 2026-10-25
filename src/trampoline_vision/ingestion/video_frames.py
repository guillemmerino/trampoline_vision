"""Accés seqüencial mandrós a píxels originals amb PTS i dimensions verificats."""

from trampoline_vision.tracking.errors import TrackingError


def validate_decoded(video, index, decoded):
    """Contrasta cada fotograma amb ffprobe abans d'utilitzar-ne els píxels per a models."""
    if decoded is None or decoded.is_corrupt or decoded.pts is None or not decoded.time_base:
        raise TrackingError(f"Invalid decoded video frame {index}")
    context = video.frame(index)
    timestamp = float(decoded.pts * decoded.time_base) - video.source_start_s
    if abs(timestamp - context.timestamp_s) > .0001 or (decoded.width, decoded.height) != (context.width_px, context.height_px):
        raise TrackingError(f"Decoded video disagrees with ffprobe at frame {index}")


class VideoFrameReader:
    """Obre el vídeo només quan es demana un píxel; no acumula imatges en memòria."""

    def __init__(self, video):
        """Conserva la línia temporal; crear el lector no importa PyAV ni obre fitxers."""
        self.video, self.container, self.frames, self.index, self.current = video, None, None, -1, None

    def get(self, index):
        """Avança fins a un índex creixent, comprovant també tots els fotogrames saltats."""
        if index < self.index:
            raise TrackingError("Video reader requires increasing frame indices")
        if self.container is None:
            try:
                import av
                self.container = av.open(str(self.video.path))
                self.frames = iter(self.container.decode(video=0))
            except (ImportError, OSError) as exc:
                raise TrackingError("Appearance video reading requires PyAV") from exc
        while self.index < index:
            self.index += 1
            self.current = next(self.frames, None)
            validate_decoded(self.video, self.index, self.current)
        return self.current

    def close(self):
        """Allibera el descodificador en finalitzar o si falla una etapa posterior."""
        if self.container is not None:
            self.container.close()
