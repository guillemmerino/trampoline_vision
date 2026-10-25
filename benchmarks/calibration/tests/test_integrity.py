"""Integritat del corpus, represa i referències independents del detector."""

from contextlib import contextmanager, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmarks.calibration.common import atomic_json, artifacts, exclusive_run, inside, read_json, sha256
from benchmarks.calibration.detector import original_boxes
from benchmarks.calibration.evaluation import evaluate, load_reference
from benchmarks.calibration.prepare import prepare
from benchmarks.calibration.run import completed, parser, resolve_plan, run


class CalibrationIntegrityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_prepare_copies_verified_sources_and_refuses_changed_inputs(self):
        source = self.root / "tfm"
        source.mkdir()
        (source / "clip.mp4").write_bytes(b"original-video")
        corpus = self.root / "corpus.json"
        atomic_json(corpus, {"schema_version": "1.0", "cases": [{"path": "videos/clip.mp4", "sha256": sha256(source / "clip.mp4"),
                                                               "source": {"root": "tfm", "path": "clip.mp4"}}], "models": []})
        target, archive = self.root / "bundle", self.root / "bundle.tar"
        with redirect_stdout(io.StringIO()):
            prepare(corpus, source, target, archive)
            prepare(corpus, source, target)
        self.assertEqual((target / "videos/clip.mp4").read_bytes(), b"original-video")
        self.assertIn(sha256(archive), Path(str(archive) + ".sha256").read_text())
        (source / "clip.mp4").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            prepare(corpus, source, target)
        self.assertEqual((target / "videos/clip.mp4").read_bytes(), b"original-video")

    def test_bundle_paths_cannot_escape_the_root(self):
        for relative in ("../escape", str(self.root.resolve()), "."):
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                inside(self.root, relative)

    def test_resume_verifies_every_artifact_and_the_run_identity(self):
        data = self.root / "trace.jsonl"
        data.write_text("complete")
        atomic_json(self.root / "completed.json", {"signature": "a", "artifacts": artifacts(self.root, [data])})
        self.assertEqual(completed(self.root, "a")["signature"], "a")
        with self.assertRaisesRegex(ValueError, "different identity"):
            completed(self.root, "b")
        data.write_text("truncated")
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            completed(self.root, "a")

    def test_partial_attempt_without_completion_is_not_a_success(self):
        (self.root / "frames.jsonl").write_text("partial")
        self.assertIsNone(completed(self.root, "run"))

    def test_os_lock_prevents_simultaneous_writers_and_releases(self):
        path = self.root / ".lock"
        with exclusive_run(path):
            with self.assertRaisesRegex(ValueError, "Another process"):
                with exclusive_run(path):
                    self.fail("Second writer acquired lock")
        with exclusive_run(path):
            pass

    def test_run_requires_explicit_resume_and_same_inputs(self):
        args = parser().parse_args(["--output", str(self.root / "run")])
        plan = {"identity": {"dataset": "a"}}
        with patch("benchmarks.calibration.run.execute_jobs", return_value=0) as jobs:
            self.assertEqual(run(args, plan, {}), 0)
            with self.assertRaisesRegex(ValueError, "Output already exists"):
                run(args, plan, {})
            args.resume = True
            self.assertEqual(run(args, plan, {}), 0)
            with self.assertRaisesRegex(ValueError, "Cannot resume"):
                run(args, {"identity": {"dataset": "b"}}, {})
        self.assertEqual(jobs.call_count, 2)

    def test_detector_resize_inverse_uses_actual_dimensions_and_retains_small_people(self):
        rows = [[0, 0, 30, 60, .8, 0], [6, 6, 9, 12, .7, 0]]
        boxes = original_boxes(rows, (40, 20), (60, 30))
        self.assertEqual(len(boxes), 2)
        self.assertEqual(boxes[0], (0., 0., 20., 40., .8))
        self.assertEqual(original_boxes(rows, (40, 20), (60, 30), 1), boxes[:1])
        with self.assertRaisesRegex(ValueError, "Non-finite"):
            original_boxes([[0, 0, float("nan"), 1, .8, 0]], (40, 20), (60, 30))

    def test_duplicate_json_options_are_rejected(self):
        path = self.root / "bad.json"
        path.write_text('{"threshold":0.1,"threshold":0.2}')
        with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
            read_json(path)


class CalibrationReferenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.case = {"case_id": "case", "sha256": "a" * 64, "video": {"frame_count": 3, "width_px": 100, "height_px": 100}}

    def write_reference(self, **overrides):
        value = {"schema_version": "1.0", "case_id": "case", "video_sha256": "a" * 64, "status": "reviewed", "reviewer": "human",
                 "samples": [{"frame_index": index, "state": "visible", "bbox_xyxy": [10, 10, 30, 50]} for index in range(3)], **overrides}
        path = self.root / "reference.json"
        atomic_json(path, value)
        return path

    def test_reference_is_bound_to_video_bytes_not_detector_ids(self):
        path = self.write_reference()
        self.assertEqual(set(load_reference(path, self.case)), {0, 1, 2})
        with self.assertRaisesRegex(ValueError, "same video"):
            load_reference(path, {**self.case, "sha256": "b" * 64})

    def test_drafts_are_not_evaluated_and_reviewed_boxes_are_required(self):
        self.assertIsNone(load_reference(self.write_reference(status="draft", reviewer=""), self.case))
        path = self.write_reference(samples=[{"frame_index": 0, "state": "visible", "bbox_xyxy": None}])
        with self.assertRaisesRegex(ValueError, "valid original-pixel"):
            load_reference(path, self.case)

    def test_provisional_references_require_explicit_opt_in(self):
        path = self.write_reference(status="provisional", reviewer="model", human_reviewed=False)
        self.assertIsNone(load_reference(path, self.case))
        self.assertEqual(set(load_reference(path, self.case, allow_provisional=True)), {0, 1, 2})

    def test_provisional_opt_in_still_validates_video_and_geometry(self):
        path = self.write_reference(status="provisional", samples=[{"frame_index": 0, "state": "visible", "bbox_xyxy": [0, 0, 1000, 20]}])
        with self.assertRaisesRegex(ValueError, "valid original-pixel"):
            load_reference(path, self.case, allow_provisional=True)
        with self.assertRaisesRegex(ValueError, "same video"):
            load_reference(path, {**self.case, "sha256": "b" * 64}, allow_provisional=True)

    def test_predictions_do_not_count_and_source_detection_ids_can_change(self):
        box = dict(x_min=10, y_min=10, x_max=30, y_max=50)
        records = []
        for index in range(3):
            records.append({"run_id": "r", "context": {"frame_index": index},
                            "candidates": [{"candidate_id": f"new-detector-{index}", "measurement": {"bbox": box}}],
                            "tracks": [{"track_id": "t1" if index < 2 else "t2", "evidence": "predicted" if index == 1 else "observed", "bbox": box}]})
        path = self.root / "frames.jsonl"
        path.write_text("".join(json.dumps(record) + "\n" for record in records))
        result = evaluate(path, load_reference(self.write_reference(), self.case))
        self.assertEqual(result["detector_available_samples"], 3)
        self.assertEqual(result["observed_matches"], 2)
        self.assertEqual(result["id_changes_between_reviewed_matches"], 1)
        self.assertEqual(result["distinct_matched_ids"], 2)

    def test_duplicate_frames_and_out_of_image_boxes_are_rejected(self):
        sample = {"frame_index": 0, "state": "visible", "bbox_xyxy": [0, 0, 10, 20]}
        for samples in ([sample, sample], [{**sample, "bbox_xyxy": [0, 0, 101, 20]}]):
            with self.subTest(samples=samples), self.assertRaises(ValueError):
                load_reference(self.write_reference(samples=samples), self.case)


class CalibrationCorpusTests(unittest.TestCase):
    def test_annotation_sample_stays_provisional_and_matches_frozen_video_hashes(self):
        root = Path(__file__).resolve().parents[1]
        corpus = {case["case_id"]: case for case in read_json(root / "corpus.json")["cases"]}
        selection = read_json(root / "annotation-pilot/selection.json")
        total = boxes = 0
        for entry in selection["cases"]:
            path = root / "annotation-pilot/references" / (entry["case_id"] + ".json")
            value = read_json(path)
            self.assertEqual(value["status"], "provisional")
            self.assertFalse(value["human_reviewed"])
            self.assertIsNone(load_reference(path, corpus[entry["case_id"]]))
            samples = load_reference(path, corpus[entry["case_id"]], allow_provisional=True)
            self.assertEqual(set(samples), set(entry["frames"]))
            total += len(samples)
            boxes += sum(sample["bbox_xyxy"] is not None for sample in samples.values())
        self.assertEqual((total, boxes), (72, 61))

    def test_frozen_corpus_has_explicit_pilot_and_no_claimed_holdout(self):
        path = Path(__file__).resolve().parents[1] / "corpus.json"
        corpus = read_json(path)
        self.assertEqual(len(corpus["cases"]), 94)
        self.assertEqual(len(corpus["suites"]["pilot"]), 18)
        self.assertEqual(len(corpus["suites"]["smoke"]), 3)
        self.assertEqual(corpus["selection_status"], "exploratory_not_independent_holdout")
        self.assertEqual(sum(case["size_bytes"] for case in corpus["cases"]), 257730723)
