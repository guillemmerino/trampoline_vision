"""Repository locations shared by CLI, runners, reports and annotation tools."""

from pathlib import Path

CALIBRATION_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = CALIBRATION_ROOT.parents[1]
CONFIG_ROOT = CALIBRATION_ROOT / "config"
EXPERIMENT_ROOT = CONFIG_ROOT / "experiments"
ITERATION_ROOT = CONFIG_ROOT / "iterations"
ANNOTATIONS_ROOT = CALIBRATION_ROOT / "annotations"
STATIC_ROOT = CALIBRATION_ROOT / "reviews/static"

# Keep historical analysis-code labels readable after moving the implementation.
SOURCE_FILES = {
    "review.py": "reviews/tracking_report.py",
    "detection_review.py": "reviews/detection_report.py",
    "detection_decisions.py": "reviews/decisions.py",
    "evaluation.py": "engine/evaluation.py",
    "sampling.py": "engine/sampling.py",
}


def source_file(name):
    return CALIBRATION_ROOT / SOURCE_FILES[name]
