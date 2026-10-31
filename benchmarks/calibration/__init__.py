"""Calibration package and import compatibility for existing offline assessments.

New code uses engine/, reviews/ and tools/. Old module names remain aliases to
the same module objects, so frozen assessment scripts and unittest patches keep
working without duplicate implementations or loose root-level wrapper files.
"""

from importlib import import_module
import sys

_LEGACY_IMPORTS = {
    "common": "engine.common", "detector": "engine.detector", "evaluation": "engine.evaluation",
    "sampling": "engine.sampling", "run": "engine.run", "iterate": "engine.iterate",
    "review": "reviews.tracking_report", "detection_review": "reviews.detection_report",
    "detection_decisions": "reviews.decisions", "human_review": "reviews.human",
    "prepare": "tools.prepare_data", "verify_corpus": "tools.verify_corpus",
    "reference_templates": "tools.reference_templates", "prepare_annotation_sample": "tools.extract_frames",
    "review_annotation_sample": "tools.render_references", "compare_annotation_sample": "tools.compare_references",
    "render_annotation_videos": "tools.render_videos",
}
for _old, _new in _LEGACY_IMPORTS.items():
    _module = import_module("." + _new, __name__)
    sys.modules[__name__ + "." + _old] = _module
    globals()[_old] = _module
