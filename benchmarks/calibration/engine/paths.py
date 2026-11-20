"""Rutes comunes del banc: inputs compartits, estudis arxivats i eines actives."""

from pathlib import Path

CALIBRATION_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = CALIBRATION_ROOT.parents[1]
CONFIG_ROOT = CALIBRATION_ROOT / "config"
ARCHIVE_ROOT = CALIBRATION_ROOT / "archive/detection-preparation-v1"
EXPERIMENT_ROOT = ARCHIVE_ROOT / "config/experiments"
ITERATION_ROOT = ARCHIVE_ROOT / "config/iterations"
ANNOTATIONS_ROOT = CALIBRATION_ROOT / "annotations"
STATIC_ROOT = CALIBRATION_ROOT / "reviews/static"

# Conserva els noms històrics del codi en llegir valoracions congelades.
SOURCE_FILES = {
    "review.py": "reviews/tracking_report.py",
    "detection_review.py": "reviews/detection_report.py",
    "detection_decisions.py": "reviews/decisions.py",
    "evaluation.py": "engine/evaluation.py",
    "sampling.py": "engine/sampling.py",
}


def source_file(name):
    """Resol l’etiqueta original d’un avaluador al seu únic fitxer executable actual."""
    return CALIBRATION_ROOT / SOURCE_FILES[name]
