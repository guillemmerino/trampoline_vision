"""Adapta OpenPose BODY_25 enregistrat al model intern, fotograma a fotograma.

Admet ZIP i carpeta de JSON. Se n'indexen els noms, però només es converteix
un fotograma de deteccions cada vegada. El ZIP es llegeix directament,
sense extreure'l. La línia temporal la fixa VideoAsset, no la presència
de registres: també es generen contexts quan falta un JSON.
"""

from contextlib import contextmanager
import math
from pathlib import Path, PurePosixPath
import re
from typing import Iterator
import zipfile

from trampoline_vision.contracts.observations import (
    BODY25_NAMES, DetectionProvenance, FrameDetections, KeypointObservation, PersonDetection, VideoAsset,
)
from trampoline_vision.ingestion.errors import DetectionFormatError, InputError
from trampoline_vision.ingestion.json_io import parse_json
from trampoline_vision.ingestion.manifest import CaseManifest

# El patró reconeix l’índex del fotograma, evitant confondre’l amb altres nombres del nom.
_FRAME_NAME = re.compile(r"(?:^|[_-])frame_?(\d+)_keypoints\.json$", re.IGNORECASE)
# Límit per registre, no per ZIP complet; acota la memòria de lectura d’un JSON.
MAX_RECORD_BYTES = 16 * 1024 * 1024


def _source_index(name: str) -> int:
    """Extreu l'índex extern d'un nom frame_NNN_keypoints.json amb prefix opcional.

    Només mira el nom final del registre i admet separadors Windows o ZIP.
    No tria qualsevol nombre del nom: podria ser l'ID del vídeo o una durada.
    El canvi a índex intern es fa després amb la base declarada al manifest.
    """
    match = _FRAME_NAME.search(PurePosixPath(name.replace("\\", "/")).name)
    if not match:
        raise DetectionFormatError(f"Cannot parse explicit frame index from JSON record: {name}")
    return int(match.group(1))


@contextmanager
def _records(path: Path):
    """Obre la font i proporciona registres i accés opcional a l'arxiu ZIP.

    És un context manager: allibera el ZIP en acabar la iteració o en cas
    d'error. Cada parella conté nom d'origen i Path o ZipInfo; encara no
    carrega ni interpreta les persones de cap fotograma.
    """
    if path.is_dir():
        files = sorted(path.rglob("*.json"))
        yield [(p.relative_to(path).as_posix(), p) for p in files], None
    else:
        # Els membres es consulten directament: no cal crear una carpeta amb tot el ZIP.
        with zipfile.ZipFile(path) as archive:
            records = [(info.filename, info) for info in archive.infolist()
                       if not info.is_dir() and info.filename.lower().endswith(".json")]
            yield records, archive


def _read_record(record, archive) -> str:
    """Llegeix un únic JSON com a text, amb límit de mida i codificació explícita.

    record és Path si és carpeta o ZipInfo si archive és un ZIP obert.
    Es comprova la mida declarada i la llegida, i es retorna text UTF-8
    amb BOM opcional. Els errors de lectura generen DetectionFormatError.
    La interpretació JSON es fa separadament amb parse_json.
    """
    try:
        if archive is None:
            if record.stat().st_size > MAX_RECORD_BYTES:
                raise DetectionFormatError(f"JSON record exceeds {MAX_RECORD_BYTES} bytes: {record}")
            with record.open("rb") as stream:
                raw = stream.read(MAX_RECORD_BYTES + 1)
        else:
            # La mida declarada del membre s’examina abans de descomprimir; després també es limita la lectura.
            if record.file_size > MAX_RECORD_BYTES:
                raise DetectionFormatError(f"JSON record exceeds {MAX_RECORD_BYTES} bytes: {record.filename}")
            with archive.open(record) as stream:
                raw = stream.read(MAX_RECORD_BYTES + 1)
        if len(raw) > MAX_RECORD_BYTES:
            raise DetectionFormatError("JSON record exceeds configured size limit")
        return raw.decode("utf-8-sig")
    except (OSError, UnicodeError, RuntimeError, zipfile.BadZipFile) as exc:
        raise DetectionFormatError(f"Cannot read OpenPose record: {exc}") from exc


def _person(person: dict, index: int, source_index: int, record_name: str,
            manifest: CaseManifest, context) -> PersonDetection:
    """Converteix una entrada people a PersonDetection amb 25 articulacions semàntiques.

    Verifica 75 nombres X/Y/confiança i el rang [0,1] de confiança. Amb
    confiança zero guarda coordenades None; amb confiança positiva conserva
    també X/Y zero i marca si el punt és dins la imatge. No filtra persones,
    no normalitza coordenades i no assigna identitats entre fotogrames.
    El context aporta dimensions i índex intern; el manifest aporta origen.
    """
    if not isinstance(person, dict):
        raise DetectionFormatError(f"Person {index} is not an object in {record_name}")
    # BODY_25 són 25 tripletes X/Y/confiança. No es descarta cap posició del vector.
    values = person.get("pose_keypoints_2d")
    if not isinstance(values, list) or len(values) != 75:
        raise DetectionFormatError(f"Expected 75 BODY_25 values for person {index} in {record_name}")
    points = []
    for joint, name in enumerate(BODY25_NAMES):
        triple = values[joint * 3:joint * 3 + 3]
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in triple):
            raise DetectionFormatError(f"Non-finite or non-numeric {name} in {record_name}, person {index}")
        x, y, confidence = map(float, triple)
        if not 0 <= confidence <= 1:
            raise DetectionFormatError(f"Confidence outside [0, 1] for {name} in {record_name}")
        # És validesa d’entrada, no qualitat alta: el llindar de confiança útil es decidirà després.
        # Una coordenada zero amb confiança positiva es conserva.
        valid = confidence > 0
        points.append(KeypointObservation(name, x if valid else None, y if valid else None,
                                         confidence, valid,
                                         (0 <= x < context.width_px and 0 <= y < context.height_px) if valid else None))
    provenance = DetectionProvenance(str(manifest.detections_path), record_name, source_index, index,
                                     manifest.variant, manifest.rotation_provenance)
    # L’ID només distingeix propostes dins d’aquest fotograma; el tracking crearà identitats.
    return PersonDetection(f"{context.frame_index}:{index}", tuple(points), provenance)


def iter_openpose_frames(manifest: CaseManifest, video: VideoAsset, *, missing_frames_policy: str = "report") -> Iterator[FrameDetections]:
    """Genera un FrameDetections per cada fotograma de la línia temporal del vídeo.

    Valida l'índex de cada registre després de restar frame_index_base.
    Rebutja duplicats, índexs fora del vídeo i JSON malformats. Amb report,
    un registre absent genera source_status=missing; amb error atura la
    lectura si falta algun registre. Un JSON amb people buit és present.

    És un generador: la lectura efectiva passa quan el consumidor itera,
    i el ZIP es manté obert durant aquesta iteració. No executa seguiment.
    """
    if missing_frames_policy not in {"report", "error"}:
        raise ValueError("Unknown missing frame policy")
    try:
        with _records(manifest.detections_path) as (records, archive):
            if not records:
                raise DetectionFormatError("No JSON records found in the detection source")
            # Indexem els registres abans de consumir-los per rebutjar duplicats i fora de rang.
            indexed = {}
            for name, record in records:
                source_index = _source_index(name)
                # La mateixa numeració interna s’utilitza per buscar temps i per exportar deteccions.
                index = source_index - manifest.frame_index_base
                if not 0 <= index < video.frame_count:
                    raise DetectionFormatError(f"Frame {source_index} in {name} is outside the video timeline")
                if index in indexed:
                    raise DetectionFormatError(f"Duplicate frame {source_index}: {indexed[index][0]} and {name}")
                indexed[index] = (name, record, source_index)
            if missing_frames_policy == "error" and len(indexed) != video.frame_count:
                raise DetectionFormatError(f"Missing {video.frame_count - len(indexed)} detection records")
            # És el vídeo qui governa la iteració: així no desapareixen fotogrames buits ni l’últim.
            for index in range(video.frame_count):
                context = video.frame(index)
                if index not in indexed:
                    # Absència de registre, diferent d’un JSON vàlid sense persones. El temps es conserva.
                    yield FrameDetections(context, (), "missing")
                    continue
                name, record, source_index = indexed[index]
                payload = parse_json(_read_record(record, archive), name)
                people = payload.get("people")
                if not isinstance(people, list):
                    raise DetectionFormatError(f"people must be an array in {name}")
                # Es conserven totes les persones, amb la posició original com a procedència.
                detections = tuple(_person(p, i, source_index, name, manifest, context) for i, p in enumerate(people))
                yield FrameDetections(context, detections, "present")
    except (InputError, OSError, zipfile.BadZipFile, RuntimeError, OverflowError) as exc:
        raise DetectionFormatError(f"OpenPose input {manifest.detections_path}: {exc}") from exc
