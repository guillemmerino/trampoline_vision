"""Lectura estricta de configuració executable de seguiment de deteccions enregistrades."""

from dataclasses import dataclass
from pathlib import Path

from trampoline_vision.ingestion.errors import InputError, ManifestError
from trampoline_vision.ingestion.json_io import read_json
from trampoline_vision.preparation.config import PreparationConfig
from trampoline_vision.tracking.config import TrackerConfig


@dataclass(frozen=True)
class TrackingPipelineConfig:
    """Configuració resolta amb rutes absolutes i components validats, sense instanciar models."""

    manifest_path: Path  # Font de vídeo i deteccions, resolta respecte del JSON de pipeline.
    preparation_path: Path  # Configuració de candidats; es protegeix també contra sortides coincidents.
    preparation: PreparationConfig  # Defaults resolts i validats.
    tracker: TrackerConfig  # Paràmetres del backend; encara no calibrats.
    missing_frames_policy: str  # report manté buits; error exigeix tots els registres.


def load_tracking_config(path: Path) -> TrackingPipelineConfig:
    """Carrega schema 1.0/task track_recorded_detections i rebutja opcions o rutes ambigües."""
    path = path.resolve()
    try:
        value = read_json(path)
        allowed = {"schema_version", "task", "case_manifest", "preparation_config", "tracker", "missing_frames_policy"}
        if set(value) - allowed or value.get("schema_version") != "1.0" or value.get("task") != "track_recorded_detections":
            raise ValueError("Expected schema 1.0 and task track_recorded_detections with known keys")
        paths = []
        for key in ("case_manifest", "preparation_config"):
            item = value[key]
            if not isinstance(item, str) or not item.strip():
                raise ValueError(f"{key} must be a path string")
            paths.append((path.parent / item).resolve())
        policy = value.get("missing_frames_policy", "report")
        if policy not in ("report", "error"):
            raise ValueError("missing_frames_policy must be report or error")
        prep = PreparationConfig.from_dict(read_json(paths[1]))
        return TrackingPipelineConfig(*paths, prep, TrackerConfig.from_dict(value.get("tracker", {})), policy)
    except (InputError, ValueError, KeyError, TypeError) as exc:
        raise ManifestError(f"Invalid tracking configuration {path}: {exc}") from exc
