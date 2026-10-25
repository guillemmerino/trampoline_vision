"""Codificació CPU del vídeo anotat amb temps explícits i sense àudio.

PyAV es carrega només en activar la visualització. Pillow dibuixa; PyAV
descodifica i codifica. La comprovació posterior amb ffprobe és independent
del codificador i verifica recompte, temps i dimensions abans de publicar.
"""

from fractions import Fraction
from pathlib import Path
from typing import Callable, Iterator

from trampoline_vision.contracts.observations import FrameDetections, VideoAsset
from trampoline_vision.results.errors import VisualizationError
from trampoline_vision.results.overlay import RenderStyle, render_frame


# Resolució temporal interna del codificador. ffprobe exposa temps a microsegons.
ENCODER_TIME_BASE = Fraction(1, 1_000_000)


def _pyav():
    """Carrega el backend opcional sense afectar inspect ni els imports del nucli."""
    try:
        import av
    except ImportError as exc:
        raise VisualizationError("Visualization requires PyAV. Install trampoline-vision[visualization] or use Docker CPU.") from exc
    return av


def _mux_packets(destination, packets, durations: dict[int, Fraction]) -> None:
    """Assigna durades explícites als paquets i els desa amb la seva base temporal.

    Evita que un canvi d'interval o un tall final es reinterpreti com a FPS
    constants. Es desactiven B-frames al codificador per simplificar la traça.
    """
    for packet in packets:
        if packet.pts is None or not packet.time_base:
            raise VisualizationError("Encoder produced a packet without presentation time")
        key = round(Fraction(packet.pts) * packet.time_base / ENCODER_TIME_BASE)
        if key not in durations:
            raise VisualizationError("Encoder packet cannot be matched to an input frame")
        packet.duration = max(1, round(durations[key] / packet.time_base))
        destination.mux(packet)


def encode_visualization(video: VideoAsset, observations: Iterator[FrameDetections], output: Path,
                         style: RenderStyle, first_index: int, stop_index: int,
                         progress: Callable[[int, int], None] | None = None, *,
                         renderer: Callable = render_frame, decoded_callback: Callable | None = None) -> dict:
    """Escriu un MP4 temporal per a l'interval [first_index, stop_index).

    Es descodifica des de l'inici per mantenir correspondència exacta d'índexs.
    Cada temps descodificat es contrasta amb ffprobe. El temps de sortida
    comença a zero, mentre la capçalera conserva el temps del vídeo original.
    Les dades es consumeixen en ordre i només es reté una imatge cada vegada.
    renderer pot dibuixar un altre contracte amb context/source_status/detections,
    com TrackingOverlayFrame; codificació i verificació temporal són compartides.
    """
    av = _pyav()
    frame_reports = []
    durations = {}
    totals = {}
    first_time = video.timestamps_s[first_index]
    try:
        with av.open(str(video.path)) as source, av.open(str(output), "w", format="mp4", options={"movflags": "+faststart"}) as destination:
            stream = None
            decoded_frames = iter(source.decode(video=0))
            for index in range(stop_index):
                decoded = next(decoded_frames, None)
                if decoded_callback is not None:
                    # El model consumeix els mateixos píxels originals que després es dibuixen.
                    from trampoline_vision.ingestion.video_frames import validate_decoded
                    validate_decoded(video, index, decoded)
                    decoded_callback(index, decoded)
                observed = next(observations, None)
                if decoded is None or observed is None:
                    raise VisualizationError(f"Video/detections ended before frame {index}")
                context = observed.context
                if context.frame_index != index or context.video_id != video.video_id:
                    raise VisualizationError("Detection contexts are not in video order")
                if decoded.is_corrupt or decoded.pts is None or not decoded.time_base:
                    raise VisualizationError(f"Invalid decoded frame {index}")
                decoded_time = float(decoded.pts * decoded.time_base) - video.source_start_s
                if abs(decoded_time - context.timestamp_s) > 0.0001:
                    raise VisualizationError(f"Decoded timestamp disagrees with ffprobe at frame {index}")
                if (decoded.width, decoded.height) != (context.width_px, context.height_px):
                    raise VisualizationError(f"Decoded dimensions disagree at frame {index}")
                if index < first_index:
                    continue
                image, stats = renderer(decoded.to_image(), observed, style)
                if stream is None:
                    rate = Fraction(str(video.fps)) if video.fps else Fraction(1 / context.duration_s).limit_denominator(100000)
                    stream = destination.add_stream("libx264", rate=rate)
                    stream.width, stream.height = image.size
                    stream.pix_fmt = "yuv420p"
                    stream.time_base = ENCODER_TIME_BASE
                    stream.codec_context.time_base = ENCODER_TIME_BASE
                    stream.codec_context.max_b_frames = 0
                    stream.options = {"crf": "20", "preset": "veryfast", "bf": "0"}
                frame = av.VideoFrame.from_image(image)
                frame.pts = round((context.timestamp_s - first_time) / float(ENCODER_TIME_BASE))
                frame.time_base = ENCODER_TIME_BASE
                durations[frame.pts] = Fraction(str(context.duration_s))
                _mux_packets(destination, stream.encode(frame), durations)
                for view, counts in stats.items():
                    accumulator = totals.setdefault(view, {name: 0 for name in counts})
                    for name, value in counts.items():
                        accumulator[name] += value
                frame_reports.append({"frame_index": index, "timestamp_s": context.timestamp_s,
                                      "source_status": observed.source_status,
                                      "source_detections": len(observed.detections), "views": stats})
                if progress:
                    progress(len(frame_reports), stop_index - first_index)
            if stop_index == video.frame_count and next(decoded_frames, None) is not None:
                raise VisualizationError("Decoder found more frames than the probed timeline")
            if stream is None:
                raise VisualizationError("No frames selected for rendering")
            _mux_packets(destination, stream.encode(), durations)
    except VisualizationError:
        raise
    except (av.FFmpegError, OSError, ValueError) as exc:
        raise VisualizationError(f"Video rendering failed: {exc}") from exc
    return {"frames": frame_reports, "totals_by_view": totals}
