"""Acceptació de l'estudi i parcialitat explícita sense reescriure IoU ni caixes."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from benchmarks.calibration.common import atomic_json, digest, read_json, sha256
from benchmarks.calibration.detection_decisions import apply_localization_review, validate_decisions
from benchmarks.calibration.iterate import main
import test_iteration as fixtures


class LocalizationDecisionTests(unittest.TestCase):
    def test_explicit_partial_and_sufficient_preserve_geometric_result(self):
        boxes = {0: [{"det_id": 17, "bbox_xyxy": [10., 10., 20., 40.], "confidence": .002}],
                 1: [{"det_id": 8, "bbox_xyxy": [40., 40., 45., 45.], "confidence": .001}]}
        rows = [{"frame_index": i, "reference_state": "visible", "detector_available": False, "max_iou": .48 if i == 0 else .2}
                for i in range(2)]
        decisions = [{"frame_index": i, "candidate": {k: boxes[i][0][k] for k in ("bbox_xyxy", "confidence")},
                      "classification": classification, "reviewer": "user", "reviewer_type": "human", "notes": "Explicit decision"}
                     for i, classification in enumerate(("sufficient", "partial"))]
        metrics = apply_localization_review(rows, boxes, decisions)
        self.assertEqual(metrics["sufficient_localization_samples"], 1)
        self.assertEqual(metrics["partial_localization_samples"], 1)
        self.assertEqual([r["max_iou"] for r in rows], [.48, .2])
        self.assertTrue(all(r["detector_available"] is False for r in rows))
        self.assertTrue(rows[1]["partial_bbox"])
        self.assertEqual(rows[1]["reviewed_candidate_id"], 8)
        self.assertTrue(rows[1]["association_candidate_available"])
        decisions[0]["candidate"]["confidence"] = .003
        with self.assertRaisesRegex(ValueError, "missing, changed"):
            apply_localization_review(rows, boxes, decisions)

    def test_low_confidence_does_not_automatically_mean_partial_or_incorrect(self):
        rows = [{"frame_index": 0, "reference_state": "visible", "detector_available": False},
                {"frame_index": 1, "reference_state": "visible", "detector_available": False},
                {"frame_index": 2, "reference_state": "ambiguous", "detector_available": None}]
        metrics = apply_localization_review(rows, {0: [{"det_id": 0, "bbox_xyxy": [0, 0, 2, 2], "confidence": .001}], 1: [], 2: []})
        self.assertEqual([r["localization_class"] for r in rows], ["needs_review", "absent_or_incorrect", "excluded"])
        self.assertEqual(metrics["needs_review_samples"], 1)
        self.assertFalse(any(r["partial_bbox"] for r in rows))

    def test_reference_acceptance_cannot_be_reused_for_a_changed_annotation(self):
        value = {"schema_version": "1.0", "review_id": "test", "reference_acceptance": [
            {"case_id": "c", "video_sha256": "a", "reference_sha256": "b", "accepted_for_study": True,
             "reviewer": "user", "notes": "Accepted for study"}], "detector_roles": {}, "decisions": []}
        self.assertEqual(validate_decisions(value, {"c": {"sha256": "a"}}, {"c": "b"}, {}, {}), value)
        with self.assertRaisesRegex(ValueError, "reference differs"):
            validate_decisions(value, {"c": {"sha256": "a"}}, {"c": "changed"}, {}, {})


@unittest.skipUnless(not getattr(fixtures.IterationTests, "__unittest_skip__", False), "Calibration runtime required")
class LocalizationIterationTests(unittest.TestCase):
    def setUp(self):
        f = fixtures.IterationTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        self.fixture = f
        exp_path = f.root / "experiment.json"
        exp = read_json(exp_path)
        exp["trackers"] = []
        exp["detectors"][0]["confidence"] = .001
        atomic_json(exp_path, exp)
        value = read_json(f.plan)
        value.update(detector_only=True, trackers=[], overlay=False, review_decisions="decisions.json")
        value["expected"]["tracking_jobs"] = 0
        atomic_json(f.plan, value)
        corpus = read_json(f.root / "corpus.json")
        case = corpus["cases"][0]
        reference_hash = sha256(f.annotations / "synthetic.json")
        decisions = {"schema_version": "1.0", "review_id": "user-review", "reference_acceptance": [
            {"case_id": "synthetic", "video_sha256": case["sha256"], "reference_sha256": reference_hash,
             "accepted_for_study": True, "reviewer": "user", "notes": "Use AI boxes as study references"}],
            "detector_roles": {"detector": "primary"}, "decisions": []}
        for index, box, classification in [(3, [10., 5., 19., 55.], "sufficient"), (5, [10., 5., 15., 15.], "partial")]:
            decisions["decisions"].append({"case_id": "synthetic", "video_sha256": case["sha256"], "reference_sha256": reference_hash,
                "detector": "detector", "detector_settings_sha256": digest(exp["detectors"][0]), "weights_sha256": corpus["models"][0]["sha256"],
                "frame_index": index, "candidate": {"bbox_xyxy": box, "confidence": .002}, "classification": classification,
                "reviewer": "user", "reviewer_type": "human", "notes": "Explicit acceptance"})
        atomic_json(f.root / "decisions.json", decisions)

    @staticmethod
    def detect(video, settings, weights, destination, device, progress=None):
        destination.write_text("frame,det_id,x1,y1,x2,y2,conf,class_id\n" + "".join(
            f"{i},0,10,5,{19 if i == 3 else 15 if i == 5 else 30},{15 if i == 5 else 55},.002,0\n" for i in range(10)))
        return {"boxes": 10, "frame_count": 10}

    def test_decisions_are_frozen_and_portable_without_claiming_full_human_review(self):
        f = self.fixture
        self.assertEqual(f.execute(detector=self.detect), 0)
        result = read_json(f.output / "review/review.json")
        row = result["rows"][0]
        self.assertEqual((row["detector_available_samples"], row["sufficient_localization_samples"], row["partial_localization_samples"]), (1, 2, 1))
        self.assertTrue(row["reference_accepted_for_study"])
        self.assertFalse(row["human_reviewed"])
        self.assertEqual(row["detector_role"], "primary")
        self.assertIn("accepten com a referència", (f.output / "REVIEW.md").read_text())
        self.assertTrue((f.output / "inputs/localization-decisions.json").exists())
        shutil.rmtree(f.data)
        shutil.rmtree(f.annotations)
        (f.root / "decisions.json").unlink()
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--output", str(f.output), "--review-only"]), 0)

    def test_review_changes_cannot_silently_resume_a_run(self):
        f = self.fixture
        self.assertEqual(f.execute(detector=self.detect), 0)
        state = (f.output / "iteration.json").read_bytes()
        decisions = read_json(f.root / "decisions.json")
        decisions["decisions"][0]["classification"] = "partial"
        atomic_json(f.root / "decisions.json", decisions)
        with self.assertRaises(SystemExit):
            f.execute([*f.args, "--resume"], detector=self.detect)
        self.assertEqual(state, (f.output / "iteration.json").read_bytes())


class LocalizationPresetTests(unittest.TestCase):
    def test_principal_and_control_use_only_existing_three_cases(self):
        here = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary) / "data"
            data.mkdir()
            shutil.copyfile(here / "config/corpus.json", data / "corpus.json")
            with patch("benchmarks.calibration.run.verify_file"), redirect_stdout(io.StringIO()) as stream:
                self.assertEqual(main(["--plan", str(here / "archive/detection-preparation-v1/config/iterations/03-localization-candidates.json"),
                                       "--dataset", str(data), "--output", str(Path(temporary) / "out"), "--dry-run"]), 0)
            result = json.loads(stream.getvalue())
            self.assertEqual((result["videos"], result["detector_jobs"], result["tracking_jobs"]), (3, 6, 0))
            self.assertEqual(result["detector_roles"], {"yolov8m-conf0001-nms070": "primary", "yolov8m-conf0002-nms070": "control"})
            experiment = read_json(here / "archive/detection-preparation-v1/config/experiments/localization-candidates.json")
            self.assertEqual([d["confidence"] for d in experiment["detectors"]], [.001, .002])
