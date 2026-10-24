"""Construeix la línia temporal del vídeo mitjançant ffprobe a CPU.

Separa executar una eina externa de convertir la seva resposta, cosa
que permet provar casos temporals sense cap vídeo real. Es conserven
temps de presentació per fotograma; els FPS informats no substitueixen
aquests temps. No s'executen models ni es retornen imatges al pipeline.
"""

from fractions import Fraction
import math
from pathlib import Path
import statistics
import subprocess

from trampoline_vision.contracts.observations import VideoAsset
from trampoline_vision.ingestion.errors import InputError, VideoProbeError
from trampoline_vision.ingestion.json_io import parse_json


def _number(value: object, label: str) -> float:
    """Converteix un camp numèric de ffprobe a float finit, rebutjant booleans.

    ffprobe sovint representa temps com a text. label identifica el camp
    en l'error; un valor absent o no numèric el gestiona el convertidor pare.
    """
    if isinstance(value, bool):
        raise ValueError(f"Invalid {label}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"Non-finite {label}")
    return result


def video_from_probe(payload: dict, path: Path, video_id: str) -> VideoAsset:
    """Converteix el JSON de ffprobe en un VideoAsset sense executar subprocessos.

    Normalitza els temps respecte del primer fotograma i n'obté les durades.
    La durada final es llegeix del darrer paquet/fotograma; si falta, s'estima
    amb intervals previs o FPS i s'afegeix un avís. Rebutja vídeo buit, temps
    absents/no creixents, dimensions variables i rotació de visualització
    pendent de normalitzar. Retorna VideoAsset o genera VideoProbeError.
    """
    try:
        streams = payload["streams"]
        if len(streams) != 1:
            raise ValueError("Expected exactly one selected video stream")
        stream = streams[0]
        width, height = int(stream["width"]), int(stream["height"])
        # Una rotació de visualització podria fer que les dimensions i les poses
        # parlessin de sistemes diferents. Exigim normalitzar-les explícitament abans.
        rotations = [entry.get("rotation", 0) for entry in stream.get("side_data_list", [])]
        rotations.append(stream.get("tags", {}).get("rotate", 0))
        if any(not math.isclose(_number(v, "rotation") % 360, 0, abs_tol=1e-6) for v in rotations):
            raise ValueError("Video has display rotation metadata; normalize the video and detections explicitly first")
        frames = payload["frames"]
        if not frames:
            raise ValueError("Video contains no decoded frames")
        # Es llegeixen temps per fotograma, també per a vídeos amb intervals variables.
        times = tuple(_number(f["best_effort_timestamp_time"], "presentation timestamp") for f in frames)
        if any(b <= a for a, b in zip(times, times[1:])):
            raise ValueError("Missing or non-increasing presentation times")
        if any(int(f.get("width", width)) != width or int(f.get("height", height)) != height for f in frames):
            raise ValueError("Variable frame dimensions are not supported")
        # Els FPS reportats són informatius i un últim recurs per a un únic fotograma.
        fps = None
        try:
            rate = float(Fraction(stream.get("avg_frame_rate", "0/0")))
            if math.isfinite(rate) and rate > 0:
                fps = rate
        except (ValueError, ZeroDivisionError):
            pass
        # Els intervals entre marques defineixen les durades excepte la darrera,
        # que no té cap fotograma següent amb el qual restar.
        durations = [b - a for a, b in zip(times, times[1:])]
        last = frames[-1].get("duration_time", frames[-1].get("pkt_duration_time"))
        warnings = []
        if last is not None and _number(last, "last frame duration") > 0:
            last_duration = float(last)
        # Si falta la durada final, fem una aproximació declarada, sense amagar-la.
        elif durations:
            last_duration = statistics.median(durations)
            warnings.append("last_frame_duration_estimated_from_timestamp_deltas")
        elif fps:
            last_duration = 1.0 / fps
            warnings.append("last_frame_duration_estimated_from_reported_fps")
        else:
            raise ValueError("Cannot determine final frame duration")
        durations.append(last_duration)
        # Restar el primer temps manté la mateixa cronologia amb inici intern a zero.
        return VideoAsset(video_id, path.resolve(), width, height, fps,
                          tuple(t - times[0] for t in times), tuple(durations), times[0], tuple(warnings))
    except (KeyError, ValueError, TypeError, OverflowError) as exc:
        raise VideoProbeError(f"Invalid video timeline for {path}: {exc}") from exc


def probe_video(path: Path, video_id: str, *, ffprobe: str = "ffprobe", timeout_s: float = 120) -> VideoAsset:
    """Executa ffprobe i converteix la resposta en la referència temporal del vídeo.

    path és el vídeo; video_id és l'ID del cas. ffprobe permet indicar una
    ruta de binari i timeout_s limita el sondeig. El procés selecciona el
    primer flux de vídeo i consulta els fotogrames, sense inferència visual.
    Captura la resposta en memòria i delega la conversió a video_from_probe.
    Un binari absent, timeout, error de descodificació o JSON incorrecte
    produeix VideoProbeError amb informació útil per a la CLI.
    """
    # S’envia una llista d’arguments, sense shell; els noms de fitxer no s’interpreten com a ordres.
    command = [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_streams", "-show_frames",
               "-show_entries", "stream=width,height,avg_frame_rate,r_frame_rate:stream_tags=rotate:stream_side_data=rotation:frame=best_effort_timestamp_time,pkt_duration_time,duration_time,width,height",
               "-of", "json", str(path.resolve())]
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=timeout_s, check=False)
    except FileNotFoundError as exc:
        raise VideoProbeError("ffprobe is unavailable. Use the Docker CPU image or install FFmpeg and add ffprobe to PATH.") from exc
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VideoProbeError(f"Video probe failed: {exc}") from exc
    # Amb -v error, stderr indica errors reals de sondeig/descodificació encara que el procés acabi amb 0.
    if result.returncode or result.stderr.strip():
        raise VideoProbeError(f"ffprobe failed for {path}: {result.stderr.strip()[:2000]}")
    try:
        payload = parse_json(result.stdout, str(path))
    except InputError as exc:
        raise VideoProbeError(str(exc)) from exc
    return video_from_probe(payload, path, video_id)
