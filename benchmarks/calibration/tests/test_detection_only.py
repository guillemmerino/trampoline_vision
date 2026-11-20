"""Detecció completa sense trackers, límit de caixes i revisió transportable."""

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from benchmarks.calibration.common import atomic_json, read_json
from benchmarks.calibration.detection_review import evaluate_detections
from benchmarks.calibration.iterate import main
import test_iteration as fixtures


class DetectionEvaluationTests(unittest.TestCase):
    def test_empty_frames_duplicates_and_max_det_are_counted_without_ids(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "boxes.csv"
            path.write_text("frame,det_id,x1,y1,x2,y2,conf,class_id\n"
                            "0,0,10,10,30,50,.005,0\n0,1,11,11,30,50,.002,0\n2,0,60,60,80,90,.1,0\n")
            case = {"video": {"frame_count": 3, "width_px": 100, "height_px": 100, "fps": 30}}
            samples = {i: {"state": "visible", "bbox_xyxy": [10, 10, 30, 50]} for i in range(3)}
            metrics, frames, boxes = evaluate_detections(path, case, samples, 2)
            self.assertEqual(metrics["detector_available_samples"], 1)
            self.assertEqual(metrics["duplicate_matching_samples"], 1)
            self.assertEqual(metrics["frames_at_max_det"], 1)
            self.assertEqual(metrics["max_boxes_in_frame"], 2)
            self.assertEqual(metrics["missing_visible_frames"], [1, 2])
            self.assertEqual(frames[1]["boxes_in_frame"], 0)
            self.assertEqual(boxes[1], [])
            with self.assertRaisesRegex(ValueError, "max_det"):
                evaluate_detections(path, case, samples, 1)


@unittest.skipUnless(not getattr(fixtures.IterationTests, "__unittest_skip__", False), "Calibration runtime required")
class DetectionOnlyIterationTests(unittest.TestCase):
    def setUp(self):
        # Reuse a fixture; do not rerun the parent test class through inheritance.
        fixture = fixtures.IterationTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        value = read_json(fixture.plan)
        value.update(title="Segona prova: detecció amb llindars baixos", detector_only=True, trackers=[], overlay=False)
        value["expected"]["tracking_jobs"] = 0
        atomic_json(fixture.plan, value)
        experiment = read_json(fixture.root / "experiment.json")
        experiment["trackers"] = []
        atomic_json(fixture.root / "experiment.json", experiment)

    def test_detector_only_exports_images_and_can_be_reviewed_without_models_or_inputs(self):
        f = self.fixture
        with patch("trampoline_vision.application.tracking.track_case", side_effect=AssertionError("Tracker must not run")):
            self.assertEqual(f.execute(), 0)
        report = read_json(f.output / "review/review.json")
        self.assertTrue(report["technical_complete"])
        self.assertTrue(report["detector_only"])
        self.assertEqual(report["rows"][0]["detector_available_samples"], 2)
        self.assertEqual(report["rows"][0]["evaluation_status"], "evaluated_provisional_sparse")
        self.assertFalse(report["rows"][0]["human_reviewed"])
        self.assertEqual(len(list((f.output / "review/images").rglob("*.jpg"))), 3)
        self.assertFalse((f.output / "run/tracking").exists())
        self.assertFalse((f.output / "run/appearance-cache").exists())
        moved = f.root / "moved"
        f.output.rename(moved)
        shutil.rmtree(f.data)
        shutil.rmtree(f.annotations)
        with redirect_stdout(io.StringIO()), patch("benchmarks.calibration.iterate.runtime", side_effect=AssertionError("No runtime needed")):
            self.assertEqual(main(["--output", str(moved), "--review-only"]), 0)
        image = next((moved / "review/images").rglob("*.jpg"))
        image.write_bytes(b"corrupt")
        with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()):
            main(["--output", str(moved), "--review-only"])

    def test_failure_and_resume_preserve_detector_attempts(self):
        f = self.fixture
        def fail(*args, **kwargs):
            raise RuntimeError("detector interrupted")
        self.assertEqual(f.execute(detector=fail), 1)
        self.assertEqual(read_json(f.output / "iteration.json")["status"], "incomplete")
        self.assertFalse(read_json(f.output / "review/review.json")["technical_complete"])
        self.assertEqual(f.execute([*f.args, "--resume"]), 0)
        self.assertTrue((f.output / "run/detections/synthetic/detector/attempt-0001").is_dir())
        self.assertTrue((f.output / "run/detections/synthetic/detector/attempt-0002").is_dir())

    def test_detector_only_plan_rejects_trackers_and_overlay(self):
        f = self.fixture
        original = read_json(f.plan)
        for key, value in (("trackers", ["ocsort"]), ("overlay", True)):
            atomic_json(f.plan, {**original, key: value})
            with self.assertRaises(SystemExit):
                f.execute()
            self.assertFalse(f.output.exists())


class LowThresholdPresetTests(unittest.TestCase):
    def test_second_executable_plan_is_bounded_and_uses_no_trackers(self):
        here = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            data = Path(temporary) / "data"
            data.mkdir()
            shutil.copyfile(here / "config/corpus.json", data / "corpus.json")
            with patch("benchmarks.calibration.run.verify_file"), redirect_stdout(io.StringIO()) as stream:
                self.assertEqual(main(["--plan", str(here / "archive/detection-preparation-v1/config/iterations/02-low-detector-thresholds.json"),
                                       "--dataset", str(data), "--output", str(output), "--dry-run"]), 0)
            result = json.loads(stream.getvalue())
            self.assertEqual((result["videos"], result["detector_jobs"], result["tracking_jobs"]), (3, 12, 0))
            self.assertTrue(result["detector_only"])
            self.assertFalse(result["overlay"])
            self.assertFalse(output.exists())
            experiment = read_json(here / "archive/detection-preparation-v1/config/experiments/low-detector-thresholds.json")
            self.assertEqual(experiment["trackers"], [])
            self.assertEqual([d["confidence"] for d in experiment["detectors"]], [.01, .005, .002, .001])
            common = [{k: v for k, v in d.items() if k not in {"id", "confidence"}} for d in experiment["detectors"]]
            self.assertTrue(all(d == common[0] for d in common))
            self.assertEqual(common[0]["max_det"], 300)

    @unittest.skipUnless(shutil.which("bash"), "Linux server shell required")
    def test_second_command_selects_its_own_plan_and_output(self):
        here = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "data").mkdir()
            (root / "data/corpus.json").write_text("{}")
            stub = root / "docker"
            stub.write_text("#!/usr/bin/env python3\nimport json,os,sys\nwith open(os.environ['CALIBRATION_TEST_DOCKER_LOG'],'a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')\n")
            stub.chmod(0o755)
            log = root / "docker.jsonl"
            env = {**os.environ, "PATH": str(root) + os.pathsep + os.environ["PATH"],
                   "CALIBRATION_DATASET": str(root / "data"), "CALIBRATION_RESULTS": str(root / "results"),
                   "CALIBRATION_ANNOTATIONS": str(here / "annotations/pilot-v1/references"), "CALIBRATION_TEST_DOCKER_LOG": str(log)}
            subprocess.run(["bash", str(here / "commands/run-low-thresholds.sh"), "--dry-run"], cwd=root, env=env, check=True, capture_output=True)
            call = next(json.loads(line) for line in log.read_text().splitlines() if json.loads(line)[0] == "run")
            self.assertIn("benchmarks.calibration", call)
            self.assertIn("iterate", call)
            self.assertEqual(call[call.index("--plan")+1], "benchmarks/calibration/archive/detection-preparation-v1/config/iterations/02-low-detector-thresholds.json")
            self.assertEqual([call[i+1] for i, key in enumerate(call) if key == "--output"][-1], "/results/low-detector-thresholds-v1")
