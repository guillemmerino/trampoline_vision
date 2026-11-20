"""Expanded sampling bounds, partitioned metrics and portable frozen review."""

import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from benchmarks.calibration.common import atomic_json, read_json, sha256
from benchmarks.calibration.iterate import main
from benchmarks.calibration.sampling import grouped_coverage, validate_sampling
import test_iteration as fixtures


class SamplingTests(unittest.TestCase):
    def setUp(self):
        self.value = {"schema_version": "1.0", "sample_id": "test", "cases": [
            {"case_id": "c", "video_sha256": "sha", "partition": "reserved", "frames": [1, 2, 3],
             "uniform_frames": [1, 2], "dense_frames": [2, 3], "legacy_frames": []}]}
        self.cases, self.refs = {"c": {"sha256": "sha"}}, {"c": {1: {}, 2: {}, 3: {}}}

    def test_valid_overlapping_strata_and_rejected_input_mismatches(self):
        self.assertEqual(validate_sampling(self.value, self.cases, self.refs), self.value)
        for key, replacement in [("video_sha256", "changed"), ("partition", "test"), ("case_id", "other"),
                                 ("frames", [1, 2]), ("uniform_frames", [True, 2]),
                                 ("dense_frames", [3, 3]), ("dense_frames", [2, 4])]:
            with self.subTest(key=key, replacement=replacement):
                value = copy.deepcopy(self.value)
                value["cases"][0][key] = replacement
                with self.assertRaises(ValueError):
                    validate_sampling(value, self.cases, self.refs)
        value = copy.deepcopy(self.value)
        value["cases"] *= 2
        with self.assertRaises(ValueError):
            validate_sampling(value, self.cases, self.refs)

    def test_groups_keep_exclusions_partitions_and_overlapping_strata_separate(self):
        def row(partition, state, utility, available, strata):
            return dict(partition=partition, detector="d", reference_state=state, localization_class=utility,
                        detector_available=available, sampling_strata=strata)
        rows = [row("development", "visible", "sufficient", True, ["uniform", "dense"]),
                row("development", "ambiguous", "excluded", None, ["uniform"]),
                row("development", "visible", "partial", False, ["dense"]),
                row("reserved", "visible", "needs_review", False, ["uniform"])]
        groups = {(g["partition"], g["stratum"]): g for g in grouped_coverage(rows)}
        all_dev, uniform, dense = [groups[("development", s)] for s in ("all_selected", "uniform", "dense")]
        self.assertEqual((all_dev["samples"], all_dev["visible_samples"], all_dev["excluded_samples"]), (3, 2, 1))
        self.assertEqual((uniform["samples"], uniform["visible_samples"], uniform["detector_available_samples"]), (2, 1, 1))
        self.assertEqual((dense["samples"], dense["sufficient"], dense["partial"]), (2, 1, 1))
        self.assertEqual(groups[("reserved", "all_selected")]["needs_review"], 1)


@unittest.skipUnless(not getattr(fixtures.IterationTests, "__unittest_skip__", False), "Calibration runtime required")
class SamplingIterationTests(unittest.TestCase):
    def setUp(self):
        f = fixtures.IterationTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        self.fixture = f
        plan = read_json(f.plan)
        plan.update(detector_only=True, trackers=[], overlay=False, sampling_plan="selection.json")
        plan["expected"]["tracking_jobs"] = 0
        atomic_json(f.plan, plan)
        exp = read_json(f.root / "experiment.json")
        exp["trackers"] = []
        atomic_json(f.root / "experiment.json", exp)
        ref = read_json(f.annotations / "synthetic.json")
        ref["samples"][-1].update(state="ambiguous", bbox_xyxy=None)
        atomic_json(f.annotations / "synthetic.json", ref)
        case = read_json(f.root / "corpus.json")["cases"][0]
        atomic_json(f.root / "selection.json", {"schema_version": "1.0", "sample_id": "synthetic-expanded", "cases": [
            {"case_id": "synthetic", "video_sha256": case["sha256"], "partition": "reserved", "frames": [3, 5, 6],
             "uniform_frames": [3, 5], "dense_frames": [5, 6], "legacy_frames": []}]})

    def test_sampling_and_grouped_report_survive_removing_original_inputs(self):
        f = self.fixture
        self.assertEqual(f.execute(), 0)
        result = read_json(f.output / "review/review.json")
        groups = {g["stratum"]: g for g in result["grouped_coverage"]}
        self.assertEqual(groups["all_selected"]["excluded_samples"], 1)
        self.assertEqual(groups["uniform"]["detector_available_samples"], 1)
        self.assertEqual(groups["dense"]["visible_samples"], 1)
        self.assertEqual(groups["uniform"]["partition"], "reserved")
        self.assertTrue((f.output / "inputs/sampling-plan.json").exists())
        self.assertIn("review/grouped-coverage.csv", read_json(f.output / "review/checksums.json"))
        shutil.rmtree(f.data)
        shutil.rmtree(f.annotations)
        (f.root / "selection.json").unlink()
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--output", str(f.output), "--review-only"]), 0)
        self.assertEqual(result["grouped_coverage"], read_json(f.output / "review/review.json")["grouped_coverage"])
        with (f.output / "review/grouped-coverage.csv").open("a") as stream:
            stream.write("tampered\n")
        with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()):
            main(["--output", str(f.output), "--review-only"])

    def test_sampling_change_rejects_resume_before_mutating_state(self):
        f = self.fixture
        self.assertEqual(f.execute(), 0)
        previous = (f.output / "iteration.json").read_bytes()
        value = read_json(f.root / "selection.json")
        value["cases"][0]["partition"] = "development"
        atomic_json(f.root / "selection.json", value)
        with self.assertRaises(SystemExit):
            f.execute([*f.args, "--resume"])
        self.assertEqual(previous, (f.output / "iteration.json").read_bytes())


class ExpandedPresetTests(unittest.TestCase):
    def test_actual_preset_is_exactly_18_videos_36_detector_jobs_without_tracking(self):
        here = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary) / "data"
            data.mkdir()
            shutil.copyfile(here / "config/corpus.json", data / "corpus.json")
            with patch("benchmarks.calibration.run.verify_file"), redirect_stdout(io.StringIO()) as stream:
                self.assertEqual(main(["--plan", str(here / "archive/detection-preparation-v1/config/iterations/04-expanded-localization.json"),
                                       "--dataset", str(data), "--output", str(Path(temporary) / "out"), "--dry-run"]), 0)
            result = json.loads(stream.getvalue())
            self.assertEqual((result["videos"], result["detector_jobs"], result["tracking_jobs"]), (18, 36, 0))
            self.assertTrue(all(r["annotated_frames"] == 80 for r in result["reference_samples"].values()))
            self.assertFalse(result["overlay"])
            self.assertFalse((Path(temporary) / "out").exists())

    def test_ai_provenance_legacy_geometry_and_reference_bound_decisions(self):
        here = Path(__file__).resolve().parents[1]
        base = here / "annotations/expanded-v1"
        selection = read_json(base / "selection.json")
        self.assertEqual(sum(c["partition"] == "reserved" for c in selection["cases"]), 6)
        self.assertEqual(sum(c["partition"] == "development" for c in selection["cases"]), 12)
        inherited = 0
        for ent in selection["cases"]:
            cid = ent["case_id"]
            self.assertEqual((len(ent["frames"]), len(ent["uniform_frames"])), (80, 48))
            ref = read_json(base / "references" / (cid + ".json"))
            self.assertEqual(ref["status"], "provisional")
            self.assertFalse(ref["human_reviewed"])
            self.assertEqual(ref["reviewer_type"], "model")
            old = here / "annotations/pilot-v1/references" / (cid + ".json")
            if old.exists():
                current = {s["frame_index"]: s for s in ref["samples"]}
                for sample in read_json(old)["samples"]:
                    expanded = current[sample["frame_index"]]
                    self.assertEqual((expanded["bbox_xyxy"], expanded["state"]), (sample["bbox_xyxy"], sample["state"]))
                    self.assertEqual(expanded["inherited_from"]["reference_sha256"], sha256(old))
                    inherited += 1
        self.assertEqual(inherited, 72)
        self.assertEqual(len(read_json(base / "localization-decisions-v1.json")["decisions"]), 4)
        self.assertEqual(sum("_AGE_2_" in c["case_id"] for c in selection["cases"]), 6)


if __name__ == "__main__":
    unittest.main()
