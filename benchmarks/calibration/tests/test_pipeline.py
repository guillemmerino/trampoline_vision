"""Bateria de vídeo/tracking, represa i fallades; inferència YOLO opcional."""

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
from unittest.mock import patch

from benchmarks.calibration.common import atomic_json, read_json, sha256
from benchmarks.calibration.detector import detect
from benchmarks.calibration.run import main


@unittest.skipUnless(util.find_spec("trackers") and util.find_spec("av") and util.find_spec("psutil") and shutil.which("ffmpeg"),
                     "Calibration CPU runtime, PyAV and FFmpeg required")
class CalibrationPipelineTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.dataset = self.root / "dataset"
        self.dataset.mkdir()
        self.video = self.dataset / "clip.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=96x64:r=10:d=1", "-c:v", "libx264", "-bf", "0", str(self.video)],
                       check=True, capture_output=True, timeout=30)
        (self.dataset / "model.pt").write_bytes(b"fake detector; network is replaced only in the test")
        case = {"case_id": "synthetic", "path": "clip.mp4", "sha256": sha256(self.video),
                "video": {"width_px": 96, "height_px": 64, "frame_count": 10, "fps": 10, "duration_s": 1}}
        corpus = {"schema_version": "1.0", "corpus_id": "synthetic", "cases": [case], "suites": {"pilot": ["synthetic"]},
                  "models": [{"model_id": "yolov8n", "path": "model.pt", "sha256": sha256(self.dataset / "model.pt")} ]}
        self.corpus = self.root / "corpus.json"
        atomic_json(self.corpus, corpus)
        atomic_json(self.dataset / "corpus.json", corpus)
        self.profile = self.root / "tracker.json"
        atomic_json(self.profile, {"schema_version": "2.0", "backend": "ocsort", "lifecycle": {"confirmation_frames": 3}})
        self.detector = {"id": "test-detector", "model": "yolov8n", "confidence": .05, "nms_iou": .7,
                         "imgsz": 128, "resize_factor": 1., "max_det": 300, "post_area_cap": None}
        self.experiment = self.root / "experiment.json"
        atomic_json(self.experiment, {"schema_version": "1.0", "experiment_id": "synthetic", "status": "experimental", "detectors": [self.detector],
                                     "trackers": [{"id": "ocsort", "profile": "tracker.json", "lifecycle": {}, "parameters": {}}]})
        self.output = self.root / "output"
        self.args = ["--corpus", str(self.corpus), "--experiment", str(self.experiment), "--dataset", str(self.dataset),
                     "--output", str(self.output), "--device", "cpu", "--threads", "1"]

    @staticmethod
    def detections(video, settings, weights, destination, device, progress=None):
        destination.write_text("frame,det_id,x1,y1,x2,y2,conf,class_id\n" + "".join(f"{index},0,10,5,30,55,.9,0\n" for index in range(10) if index != 5))
        return {"boxes": 9, "frame_count": 10, "elapsed_s": 0}

    def test_full_pipeline_resume_corruption_and_real_identity_recovery(self):
        with patch("benchmarks.calibration.run.runtime", return_value={"test": "synthetic"}), \
             patch("benchmarks.calibration.run.detect", side_effect=self.detections) as detector, redirect_stdout(io.StringIO()):
            self.assertEqual(main(self.args), 0)
            checkpoint = read_json(self.output / "tracking/synthetic/test-detector/ocsort/completed.json")
            attempt = self.output / "tracking/synthetic/test-detector/ocsort" / checkpoint["attempt"]
            report = read_json(attempt / "tracking.json")
            self.assertEqual(report["events_in_selected_range"]["recovered"], 1)
            self.assertEqual(report["totals"]["source_detections"], 9)
            frames = [json.loads(line) for line in (attempt / "frames.jsonl").read_text().splitlines()]
            self.assertEqual(len(frames), 10)
            self.assertEqual(frames[5]["tracks"][0]["evidence"], "predicted")
            self.assertEqual(frames[4]["tracks"][0]["track_id"], frames[6]["tracks"][0]["track_id"])
            self.assertEqual(main([*self.args, "--resume"]), 0)
            self.assertEqual(detector.call_count, 1)
            (attempt / "frames.jsonl").write_text("corrupt")
            self.assertEqual(main([*self.args, "--resume"]), 1)
        summary = read_json(self.output / "summary.json")
        self.assertEqual(summary["runs"][0]["status"], "failed")
        self.assertIn("SHA-256 mismatch", summary["runs"][0]["error"])

    def test_failed_detector_can_resume_and_retry_without_erasing_attempts(self):
        def fail(video, settings, weights, destination, device, progress=None):
            destination.write_text("interrupted csv")
            raise RuntimeError("simulated interruption")
        with patch("benchmarks.calibration.run.runtime", return_value={}), \
             patch("benchmarks.calibration.run.detect", side_effect=fail), redirect_stdout(io.StringIO()):
            self.assertEqual(main(self.args), 1)
        with patch("benchmarks.calibration.run.runtime", return_value={}), \
             patch("benchmarks.calibration.run.detect", side_effect=self.detections), redirect_stdout(io.StringIO()):
            self.assertEqual(main([*self.args, "--resume"]), 0)
        attempts = self.output / "detections/synthetic/test-detector"
        self.assertEqual((attempts / "attempt-0001/boxes.csv").read_text(), "interrupted csv")
        self.assertTrue((attempts / "attempt-0002/boxes.csv").is_file())

    def test_plan_rejects_unknown_options_before_creating_output(self):
        value = read_json(self.experiment)
        value["detectors"][0]["typo_threshold"] = .1
        atomic_json(self.experiment, value)
        with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()):
            main([*self.args, "--dry-run"])
        self.assertFalse(self.output.exists())

    def test_one_failed_variant_does_not_stop_other_variants(self):
        value = read_json(self.experiment)
        value["detectors"] = [{**self.detector, "id": "bad"}, {**self.detector, "id": "good"}]
        atomic_json(self.experiment, value)
        def conditional(video, settings, weights, destination, device, progress=None):
            if settings["id"] == "bad":
                raise RuntimeError("one failed variant")
            return self.detections(video, settings, weights, destination, device, progress)
        with patch("benchmarks.calibration.run.runtime", return_value={}), \
             patch("benchmarks.calibration.run.detect", side_effect=conditional), redirect_stdout(io.StringIO()):
            self.assertEqual(main(self.args), 1)
        rows = read_json(self.output / "summary.json")["runs"]
        self.assertEqual([row["status"] for row in rows], ["detector_failed", "succeeded"])

    def test_provisional_reference_results_keep_their_model_provenance(self):
        annotations = self.root / "annotations"
        annotations.mkdir()
        atomic_json(annotations / "synthetic.json", {"schema_version": "1.0", "case_id": "synthetic",
                    "video_sha256": sha256(self.video), "status": "provisional", "reviewer": "model", "human_reviewed": False,
                    "samples": [{"frame_index": index, "state": "visible", "bbox_xyxy": [10, 5, 30, 55]} for index in (3, 5, 6)]})
        with patch("benchmarks.calibration.run.runtime", return_value={}), \
             patch("benchmarks.calibration.run.detect", side_effect=self.detections), redirect_stdout(io.StringIO()):
            self.assertEqual(main([*self.args, "--annotations", str(annotations)]), 0)
            self.assertEqual(read_json(self.output / "summary.json")["runs"][0]["reference_status"], "not_evaluated")
            other = self.root / "provisional-run"
            self.assertEqual(main([*self.args, "--output", str(other), "--annotations", str(annotations), "--allow-provisional-references"]), 0)
        complete = read_json(other / "tracking/synthetic/test-detector/ocsort/completed.json")
        self.assertEqual(complete["evaluation"]["status"], "evaluated_provisional_sparse")
        self.assertFalse(complete["evaluation"]["reference"]["human_reviewed"])
        self.assertEqual(complete["evaluation"]["observed_matches"], 2)

    @unittest.skipUnless(os.environ.get("CALIBRATION_TEST_WEIGHTS"), "Set CALIBRATION_TEST_WEIGHTS for real offline YOLO inference")
    def test_real_yolo_decodes_every_synthetic_frame_with_local_weights(self):
        from trampoline_vision.ingestion.video import probe_video
        weights = Path(os.environ["CALIBRATION_TEST_WEIGHTS"])
        video = probe_video(self.video, "synthetic")
        result = detect(video, self.detector, weights, self.root / "real-boxes.csv", "cpu")
        self.assertEqual(result["frame_count"], 10)
        self.assertEqual(result["boxes"], 0)
        self.assertEqual(result["empty_detection_frames"], 10)
