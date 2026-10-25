"""Lectura estricta de pipelines, perfils de tracker i models d'aparença amb rutes locals."""

from dataclasses import dataclass
from pathlib import Path

from trampoline_vision.ingestion.errors import InputError, ManifestError
from trampoline_vision.ingestion.json_io import read_json
from trampoline_vision.preparation.config import PreparationConfig
from trampoline_vision.tracking.config import TrackerConfig


def _path(parent, value, name):
    """Resol una ruta respecte del fitxer que la declara, sense dependre del directori actual."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a path string")
    return (parent / value).resolve()


def _appearance(path):
    """Llegeix el model d'aparença i resol pesos/cache sense instanciar cap xarxa."""
    value = read_json(path)
    allowed = {"schema_version", "provider", "weights", "sha256", "device", "cache_dir", "threads"}
    if set(value) - allowed or value.get("schema_version") != "1.0":
        raise ValueError("Appearance model requires schema 1.0 and known keys")
    result = {key: item for key, item in value.items() if key != "schema_version"}
    weights = _path(path.parent, result.get("weights"), "appearance weights")
    if not weights.is_file():
        raise ValueError(f"Local appearance weights do not exist: {weights}")
    result["weights"] = str(weights)
    if result.get("cache_dir") is not None:
        result["cache_dir"] = str(_path(path.parent, result["cache_dir"], "appearance cache_dir"))
    return result


@dataclass(frozen=True)
class TrackingPipelineConfig:
    """Configuració executable resolta, sense biblioteques opcionals ni inferència."""

    manifest_path: Path
    preparation_path: Path | None
    preparation: PreparationConfig
    tracker: TrackerConfig
    missing_frames_policy: str
    tracker_path: Path | None = None
    appearance_path: Path | None = None

    @property
    def protected_paths(self):
        """Declara fitxers de configuració i pesos que mai poden ser destinacions d'exportació."""
        paths = tuple(p for p in (self.preparation_path, self.tracker_path, self.appearance_path) if p is not None)
        return paths + ((Path(self.tracker.appearance.weights),) if self.tracker.appearance else ())


def load_tracking_config(path: Path) -> TrackingPipelineConfig:
    """Resol perfils 2.0 i manté pipelines inline 1.0, rebutjant combinacions ambigües."""
    path = path.resolve()
    try:
        value = read_json(path)
        allowed = {"schema_version", "task", "case_manifest", "preparation_config", "tracker", "tracker_config", "missing_frames_policy"}
        if set(value) - allowed or value.get("schema_version") not in ("1.0", "2.0") or value.get("task") != "track_recorded_detections":
            raise ValueError("Expected executable tracking schema 1.0 or 2.0 with known keys")
        if "tracker" in value and "tracker_config" in value:
            raise ValueError("Choose tracker_config or inline tracker, not both")
        if value["schema_version"] == "2.0" and "tracker_config" not in value:
            raise ValueError("Tracking schema 2.0 requires tracker_config")
        manifest = _path(path.parent, value.get("case_manifest"), "case_manifest")
        preparation_path = (_path(path.parent, value["preparation_config"], "preparation_config")
                            if "preparation_config" in value else None)
        preparation = PreparationConfig.from_dict(read_json(preparation_path)) if preparation_path else PreparationConfig()
        policy = value.get("missing_frames_policy", "report")
        if policy not in ("report", "error"):
            raise ValueError("missing_frames_policy must be report or error")
        tracker_path = appearance_path = None
        if "tracker_config" in value:
            tracker_path = _path(path.parent, value["tracker_config"], "tracker_config")
            profile = read_json(tracker_path)
            if profile.get("schema_version") != "2.0":
                raise ValueError("Referenced tracker profile must declare schema 2.0")
            if profile.get("appearance") is not None:
                declaration = profile["appearance"]
                if not isinstance(declaration, dict) or set(declaration) != {"model_config"}:
                    raise ValueError("Appearance must reference one model_config or be null")
                appearance_path = _path(tracker_path.parent, declaration["model_config"], "appearance model_config")
                profile["appearance"] = _appearance(appearance_path)
            tracker = TrackerConfig.from_dict(profile)
        else:
            tracker = TrackerConfig.from_dict(value.get("tracker", {}))
        return TrackingPipelineConfig(manifest, preparation_path, preparation, tracker, policy, tracker_path, appearance_path)
    except (InputError, ValueError, KeyError, TypeError) as exc:
        raise ManifestError(f"Invalid tracking configuration {path}: {exc}") from exc
