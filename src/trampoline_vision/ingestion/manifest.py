"""Connecta les fonts externes amb un cas d'anàlisi explícit.

El manifest associa vídeo i deteccions i declara índexs i coordenades.
La configuració d'inspecció només indica quin manifest usar i com tractar
registres absents. Les rutes es resolen respecte del fitxer que les declara,
perquè executar la CLI des d'una altra carpeta no canviï les entrades.
"""

from dataclasses import dataclass
from pathlib import Path
import math

from trampoline_vision.ingestion.errors import InputError, ManifestError
from trampoline_vision.ingestion.json_io import read_json


@dataclass(frozen=True)
class CaseManifest:
    """Cas d'entrada resolt i validat per al lector enregistrat.

    Conté rutes absolutes, base d'índex i procedència declarada. expected
    guarda valors que després es comparen amb el vídeo real: no substitueixen
    el sondeig. declared_reference_duration_s serveix per informar discrepàncies;
    no es carreguen ni utilitzen les notes esportives del CSV de referència.
    """
    path: Path  # Ruta absoluta del manifest per traçabilitat.
    case_id: str  # Identificador compartit per vídeo, contexts i informe.
    video_path: Path  # Ruta del vídeo resolta respecte de la carpeta del manifest.
    detections_path: Path  # ZIP o carpeta de JSON validada abans de començar la lectura.
    frame_index_base: int  # 0 o 1 explícit per traduir números externs a índex intern.
    variant: str  # Procedència general de les deteccions, conservada sense reinterpretar-la.
    rotation_provenance: str  # Informació coneguda d’orientació, o unknown.
    expected: dict  # Metadades de referència per comparar, no per substituir el vídeo real.
    declared_reference_duration_s: float | None  # Durada externa opcional; una diferència genera avís.
    known_issues: tuple[str, ...]  # Limitacions declarades del cas que es traslladen a l’informe.


def load_manifest(path: Path) -> CaseManifest:
    """Carrega un manifest 1.0 i comprova que es pugui interpretar sense inferències ocultes.

    Entrades: ruta del manifest. Retorna: CaseManifest amb fonts resoltes.
    Exigeix esquema BODY_25, coordenades originals i base 0 o 1 explícita;
    comprova tipus, existència de fonts i valors esperats positius i finits.
    Genera ManifestError amb context si manca informació o no és compatible.
    No descodifica vídeo ni llegeix encara els registres OpenPose.
    """
    path = path.resolve()
    try:
        obj = read_json(path)
        if obj.get("schema_version") != "1.0":
            raise ValueError("Manifest schema_version must be 1.0")
        if obj.get("path_base") != "manifest_directory":
            raise ValueError("path_base must be manifest_directory")
        case_id = obj["case_id"]
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("case_id must be a non-empty string")
        video = obj["video"]
        detections = obj["detections"]["primary"]
        if detections["format"] not in {"openpose_json_zip", "openpose_json_directory"}:
            raise ValueError("Only OpenPose JSON ZIP/directory sources are implemented")
        if detections["skeleton_schema"] != "openpose_body25":
            raise ValueError("Only openpose_body25 is supported")
        if detections["coordinate_space"] != "original_frame_pixels":
            raise ValueError("Preconvert detections to original_frame_pixels before replay")
        base = detections["frame_index_base"]
        if type(base) is not int or base not in {0, 1}:
            raise ValueError("frame_index_base must explicitly be 0 or 1")
        # Cada font es resol des del manifest, tant al sistema local com dins de Docker.
        resolved = []
        for entry in (video, detections):
            value = entry["path"]
            if not isinstance(value, str) or not value:
                raise ValueError("Source paths must be non-empty strings")
            resolved.append((path.parent / value).resolve())
        if not resolved[0].is_file():
            raise ValueError(f"Video does not exist: {resolved[0]}")
        if detections["format"] == "openpose_json_zip" and not resolved[1].is_file():
            raise ValueError(f"Detection ZIP does not exist: {resolved[1]}")
        if detections["format"] == "openpose_json_directory" and not resolved[1].is_dir():
            raise ValueError(f"Detection directory does not exist: {resolved[1]}")
        # Aquests valors només són referències. inspection els compararà amb el vídeo sondejat.
        expected = video.get("expected", {})
        if not isinstance(expected, dict):
            raise ValueError("video.expected must be an object")
        for key, value in expected.items():
            if key not in {"width_px", "height_px", "fps", "frame_count", "duration_s"}:
                raise ValueError(f"Unknown expected video field: {key}")
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"Invalid expected value for {key}")
        # Només recollim la durada declarada aquí. Les notes S1…S10 no entren a l’anàlisi.
        reference = obj.get("reference_metadata", {})
        if not isinstance(reference, dict):
            raise ValueError("reference_metadata must be an object")
        duration = reference.get("declared_duration_s")
        if duration is not None and (isinstance(duration, bool) or not isinstance(duration, (float, int)) or not math.isfinite(duration) or duration <= 0):
            raise ValueError("Invalid reference duration")
        issues = obj.get("known_issues", [])
        if not isinstance(issues, list) or not all(isinstance(s, str) for s in issues):
            raise ValueError("known_issues must be a list of strings")
        return CaseManifest(path, case_id, *resolved, base,
                            str(detections.get("variant", "recorded")),
                            str(detections.get("rotation_provenance", "unknown")),
                            expected, duration, tuple(issues))
    except (InputError, ValueError, TypeError, KeyError) as exc:
        raise ManifestError(f"Invalid manifest {path}: {exc}") from exc


def load_inspection_config(path: Path) -> tuple[Path, str]:
    """Resol la configuració executable del pas 2 i retorna manifest i política de buits.

    Només admet les claus de la tasca inspect_recorded_detections versió 1.0.
    Rebutja els pipelines design-only per evitar que semblin executables.
    La política report conserva buits amb avisos; error exigeix tots els registres.
    """
    path = path.resolve()
    try:
        obj = read_json(path)
        # Una configuració del pipeline futur no s’ha d’executar parcialment per accident.
        allowed = {"schema_version", "task", "case_manifest", "missing_frames_policy"}
        if set(obj) - allowed:
            raise ValueError(f"Unknown configuration keys: {sorted(set(obj) - allowed)}")
        if obj.get("schema_version") != "1.0" or obj.get("task") != "inspect_recorded_detections":
            raise ValueError("Expected schema 1.0 and task inspect_recorded_detections; design-only pipelines are not executable")
        policy = obj.get("missing_frames_policy", "report")
        if policy not in {"report", "error"}:
            raise ValueError("missing_frames_policy must be report or error")
        value = obj["case_manifest"]
        if not isinstance(value, str) or not value:
            raise ValueError("case_manifest must be a path string")
        return (path.parent / value).resolve(), policy
    except (InputError, ValueError, KeyError, TypeError) as exc:
        raise ManifestError(f"Invalid inspection configuration {path}: {exc}") from exc
