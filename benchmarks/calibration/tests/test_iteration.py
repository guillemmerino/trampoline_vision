"""Traspàs entre sessions, immutabilitat d'inputs i fallades visibles d'una iteració."""

from contextlib import redirect_stdout
from importlib import util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from benchmarks.calibration.common import atomic_json, read_json, sha256
from benchmarks.calibration.evaluation import evaluate
from benchmarks.calibration.iterate import main, prepare


class FixedIdentityEvaluationTests(unittest.TestCase):
    def test_fixed_id_counts_alternatives_and_never_counts_predictions_as_observations(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "frames.jsonl"
            exact = dict(x_min=10, y_min=10, x_max=30, y_max=50)
            smaller = {**exact, "x_max": 29}
            frames = []
            for index in range(3):
                tracks = [{"track_id": "fixed", "bbox": smaller, "evidence": "predicted" if index == 2 else "observed"}]
                if index < 2:
                    tracks.append({"track_id": f"other-{index}", "bbox": exact, "evidence": "observed"})
                frames.append({"run_id": "one", "context": {"frame_index": index}, "candidates": [], "tracks": tracks})
            path.write_text("".join(json.dumps(f) + "\n" for f in frames))
            samples = {index: {"state": "visible", "bbox_xyxy": [10, 10, 30, 50]} for index in range(3)}
            result = evaluate(path, samples)
            self.assertEqual(result["observed_matches"], 2)
            self.assertEqual(result["id_changes_between_reviewed_matches"], 1)
            self.assertEqual(result["best_fixed_id"], "fixed")
            self.assertEqual(result["best_fixed_id_observed_matches"], 2)
            self.assertEqual(result["seed_fixed_id_observed_matches"], 1)
            self.assertEqual(result["samples_with_matching_prediction_only"], 1)


@unittest.skipUnless(util.find_spec("trampoline_vision"), "Current project package required")
class RobustThresholdPlanTests(unittest.TestCase):
    def test_default_plan_bounds_and_effective_thresholds(self):
        here = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = root / "data"
            data.mkdir()
            shutil.copyfile(here / "config/corpus.json", data / "corpus.json")
            args = SimpleNamespace(plan=here / "config/iterations/01-threshold-robustness.json", corpus=here / "config/corpus.json",
                                   dataset=data, output=root / "results", annotations=None, device="cpu", threads=1, resume=False)
            # This test resolves the real preset/configurations, without video/model inference.
            with patch("benchmarks.calibration.run.verify_file"):
                value, parsed, plan = prepare(args)
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    self.assertEqual(main(["--dataset", str(data), "--output", str(args.output), "--device", "cpu", "--dry-run"]), 0)
            self.assertFalse(args.output.exists())
            summary = json.loads(buffer.getvalue())
            self.assertEqual(summary["title"], "Prova robusta de llindar")
            self.assertEqual((summary["videos"], summary["detector_jobs"], summary["tracking_jobs"]), (3, 12, 48))
            self.assertTrue(parsed.overlay)
            self.assertEqual([d["confidence"] for d in plan["detectors"]], [.01, .02, .05, .1])
            settings = [{k: v for k, v in d.items() if k not in {"id", "confidence"}} for d in plan["detectors"]]
            self.assertTrue(all(d == settings[0] for d in settings))
            self.assertEqual((settings[0]["model"], settings[0]["nms_iou"]), ("yolov8m", .7))
            for tracker in plan["trackers"]:
                config = tracker["config"]
                self.assertEqual((config.confidence_threshold, config.confirmation_frames, config.max_lost_s), (.1, 3, .5))
                if tracker["id"] != "ocsort":
                    self.assertEqual(config.parameters.low_confidence, .01)
                    self.assertEqual(plan["identity"]["profiles"][tracker["id"]]["profile"]["parameters"]["low_confidence"], .02)

    @unittest.skipUnless(shutil.which("bash"), "Linux server shell required")
    def test_server_command_uses_iteration_runner_and_robust_output(self):
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
            subprocess.run(["bash", str(here / "commands/run-iteration.sh"), "--dry-run"], cwd=root, env=env, check=True, capture_output=True)
            calls = [json.loads(line) for line in log.read_text().splitlines()]
            run_call = next(call for call in calls if call[0] == "run")
            self.assertIn("benchmarks.calibration", run_call)
            self.assertIn("iterate", run_call)
            self.assertEqual([run_call[i+1] for i, arg in enumerate(run_call) if arg == "--output"][-1], "/results/threshold-robustness-v1")
            self.assertIn("--dry-run", run_call)


@unittest.skipUnless(util.find_spec("trackers") and util.find_spec("av") and util.find_spec("psutil") and shutil.which("ffmpeg"),
                     "Calibration runtime required")
class IterationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.data = self.root / "data"
        self.data.mkdir()
        video = self.data / "clip.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=96x64:r=10:d=1",
                        "-c:v", "libx264", "-bf", "0", str(video)], check=True, capture_output=True)
        (self.data / "model.pt").write_bytes(b"test detector")
        case = {"case_id": "synthetic", "path": "clip.mp4", "sha256": sha256(video),
                "video": {"width_px": 96, "height_px": 64, "frame_count": 10, "fps": 10, "duration_s": 1}}
        corpus = {"schema_version": "1.0", "cases": [case], "suites": {"pilot": ["synthetic"]},
                  "models": [{"model_id": "yolov8n", "path": "model.pt", "sha256": sha256(self.data / "model.pt")} ]}
        atomic_json(self.root / "corpus.json", corpus)
        atomic_json(self.data / "corpus.json", corpus)
        atomic_json(self.root / "tracker.json", {"schema_version": "2.0", "backend": "ocsort"})
        atomic_json(self.root / "experiment.json", {"schema_version": "1.0", "experiment_id": "test", "status": "experimental",
                    "detectors": [{"id": "detector", "model": "yolov8n", "confidence": .05, "nms_iou": .7,
                                   "imgsz": 128, "resize_factor": 1., "max_det": 300, "post_area_cap": None}],
                    "trackers": [{"id": "ocsort", "profile": "tracker.json", "lifecycle": {}, "parameters": {}}]})
        self.annotations = self.root / "annotations"
        self.annotations.mkdir()
        atomic_json(self.annotations / "synthetic.json", {"schema_version": "1.0", "case_id": "synthetic", "video_sha256": case["sha256"],
                    "status": "provisional", "reviewer": "test model", "human_reviewed": False,
                    "samples": [{"frame_index": index, "state": "visible", "bbox_xyxy": [10, 5, 30, 55]} for index in (3, 5, 6)]})
        self.plan = self.root / "iteration.json"
        atomic_json(self.plan, {"schema_version": "1.0", "iteration_id": "test", "objective": "test", "hypothesis": "test",
                    "experiment": "experiment.json", "suite": "pilot", "cases": ["synthetic"], "detectors": ["detector"],
                    "trackers": ["ocsort"], "annotations": "annotations", "allow_provisional_references": True,
                    "overlay": True, "expected": {"videos": 1, "detector_jobs": 1, "tracking_jobs": 1}})
        self.output = self.root / "output"
        self.args = ["--plan", str(self.plan), "--corpus", str(self.root / "corpus.json"), "--dataset", str(self.data),
                     "--output", str(self.output), "--device", "cpu", "--threads", "1"]

    @staticmethod
    def detect(video, settings, weights, destination, device, progress=None):
        destination.write_text("frame,det_id,x1,y1,x2,y2,conf,class_id\n" +
                               "".join(f"{i},0,10,5,30,55,.9,0\n" for i in range(10) if i != 5))
        return {"boxes": 9, "frame_count": 10}

    def execute(self, args=None, detector=None):
        with patch("benchmarks.calibration.iterate.runtime", return_value={"test": "frozen"}), \
                patch("benchmarks.calibration.run.detect", side_effect=detector or self.detect), redirect_stdout(io.StringIO()):
            return main(args or self.args)

    def test_handover_survives_moving_the_iteration_and_removing_original_inputs(self):
        value = read_json(self.plan)
        value["title"] = "Prova robusta de llindar"
        atomic_json(self.plan, value)
        self.assertEqual(self.execute(), 0)
        state = read_json(self.output / "iteration.json")
        self.assertEqual(state["status"], "ready_for_review")
        self.assertEqual(state["title"], "Prova robusta de llindar")
        self.assertTrue((self.output / "REVIEW.md").read_text().startswith("# Prova robusta de llindar\n"))
        review = read_json(self.output / "review/review.json")
        row = review["rows"][0]
        self.assertEqual(row["observed_matches"], 2)
        self.assertEqual(row["prediction_only_samples"], 1)
        self.assertFalse(row["human_reviewed"])
        self.assertTrue((self.output / row["mp4"]).is_file())
        self.assertIn("Una mostra és UN fotograma", (self.output / "REVIEW.md").read_text())
        shutil.rmtree(self.data)
        shutil.rmtree(self.annotations)
        moved = self.root / "moved"
        self.output.rename(moved)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--output", str(moved), "--review-only"]), 0)
        self.assertTrue((moved / read_json(moved / "review/review.json")["rows"][0]["mp4"]).is_file())

    def test_failed_work_is_reviewable_and_resume_preserves_failed_attempt(self):
        def fail(*args, **kwargs):
            raise RuntimeError("interrupted detector")
        self.assertEqual(self.execute(detector=fail), 1)
        self.assertFalse(read_json(self.output / "review/review.json")["technical_complete"])
        self.assertEqual(read_json(self.output / "iteration.json")["status"], "incomplete")
        self.assertEqual(self.execute([*self.args, "--resume"]), 0)
        detection = self.output / "run/detections/synthetic/detector"
        self.assertTrue((detection / "attempt-0001").is_dir())
        self.assertTrue((detection / "attempt-0002").is_dir())

    def test_preflight_failure_has_a_handover_and_can_resume_without_a_run(self):
        with patch("benchmarks.calibration.iterate.runtime", side_effect=RuntimeError("GPU unavailable")), \
                self.assertRaises(SystemExit), redirect_stdout(io.StringIO()):
            main(self.args)
        self.assertEqual(read_json(self.output / "iteration.json")["status"], "failed")
        self.assertIn("GPU unavailable", (self.output / "REVIEW.md").read_text())
        self.assertIn("GPU unavailable", (self.output / "execution.log").read_text())
        self.assertFalse((self.output / "run").exists())
        self.assertEqual(self.execute([*self.args, "--resume"]), 0)

    def test_wrong_job_bounds_and_missing_references_fail_before_creating_output(self):
        value = read_json(self.plan)
        value["expected"]["tracking_jobs"] = 2
        atomic_json(self.plan, value)
        with self.assertRaises(SystemExit):
            self.execute()
        self.assertFalse(self.output.exists())
        value["expected"]["tracking_jobs"] = 1
        atomic_json(self.plan, value)
        (self.annotations / "synthetic.json").unlink()
        with self.assertRaises(SystemExit):
            self.execute()
        self.assertFalse(self.output.exists())

    def test_changed_plan_cannot_resume_or_overwrite_a_completed_review(self):
        self.assertEqual(self.execute(), 0)
        previous = (self.output / "iteration.json").read_bytes()
        report = (self.output / "REVIEW.md").read_bytes()
        value = read_json(self.plan)
        value["hypothesis"] = "changed"
        atomic_json(self.plan, value)
        with self.assertRaises(SystemExit):
            self.execute([*self.args, "--resume"])
        self.assertEqual((self.output / "iteration.json").read_bytes(), previous)
        self.assertEqual((self.output / "REVIEW.md").read_bytes(), report)

    def test_corrupt_trace_is_rejected_by_an_independent_review(self):
        self.assertEqual(self.execute(), 0)
        trace = next((self.output / "run/tracking").rglob("frames.jsonl"))
        trace.write_text("corrupt")
        with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()):
            main(["--output", str(self.output), "--review-only"])
