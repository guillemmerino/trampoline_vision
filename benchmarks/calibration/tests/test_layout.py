"""Public entry points and offline compatibility after grouping calibration code."""

from contextlib import redirect_stdout
from importlib import import_module
import io
from pathlib import Path
import unittest
from unittest.mock import patch

from benchmarks.calibration.__main__ import main
from benchmarks.calibration.engine.paths import ANNOTATIONS_ROOT, CONFIG_ROOT, EXPERIMENT_ROOT, PROJECT_ROOT, STATIC_ROOT, source_file
from benchmarks.calibration.engine.run import parser
from benchmarks.calibration.reviews.human import DEFAULT_RUN, DEFAULT_RAW


class CalibrationLayoutTests(unittest.TestCase):
    def test_no_command_prints_navigation_without_starting_an_experiment(self):
        with patch("benchmarks.calibration.engine.run.run") as run, \
                patch("benchmarks.calibration.engine.iterate.main") as iterate, \
                redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main([]), 0)
        self.assertIn("review", output.getvalue())
        run.assert_not_called()
        iterate.assert_not_called()

    def test_review_command_forwards_arguments_to_the_same_human_review(self):
        args = ["assess", "--decisions", "/tmp/review.json", "--output", "/tmp/new-assessment"]
        with patch("benchmarks.calibration.reviews.human.main", return_value=0) as review:
            self.assertEqual(main(["review", *args]), 0)
        review.assert_called_once_with(args)

    def test_study_wrapper_preserves_explicit_scope_and_forwarded_flags(self):
        with patch("benchmarks.calibration.__main__.os.execvp", side_effect=SystemExit(0)) as execute:
            with self.assertRaises(SystemExit):
                main(["study", "expanded", "--dry-run"])
        program, argv = execute.call_args.args
        self.assertEqual(program, "bash")
        self.assertTrue(Path(argv[1]).is_file())
        self.assertEqual(Path(argv[1]).name, "run-expanded-localization.sh")
        self.assertEqual(argv[2:], ["--dry-run"])

    def test_defaults_find_configs_assets_and_existing_run_locations(self):
        args = parser().parse_args([])
        self.assertEqual(args.corpus, CONFIG_ROOT / "corpus.json")
        self.assertEqual(args.experiment, EXPERIMENT_ROOT / "baseline.json")
        self.assertTrue(args.corpus.is_file())
        self.assertTrue(args.experiment.is_file())
        self.assertTrue((ANNOTATIONS_ROOT / "expanded-v1/references").is_dir())
        self.assertEqual(DEFAULT_RUN, PROJECT_ROOT / "runs/calibration/expanded-localization-v1")
        self.assertEqual(DEFAULT_RAW, PROJECT_ROOT / "runs/calibration/sample-expansion-preparation-v1/raw")
        self.assertTrue(all((STATIC_ROOT / ("human_review." + suffix)).is_file() for suffix in ("html", "js", "css")))

    def test_historical_imports_share_module_objects_and_source_identity(self):
        pairs = {"run": "engine.run", "iterate": "engine.iterate", "evaluation": "engine.evaluation",
                 "review": "reviews.tracking_report", "human_review": "reviews.human",
                 "detection_review": "reviews.detection_report", "prepare": "tools.prepare_data"}
        for old, new in pairs.items():
            self.assertIs(import_module("benchmarks.calibration." + old), import_module("benchmarks.calibration." + new))
        self.assertEqual(source_file("evaluation.py"), Path(import_module("benchmarks.calibration.evaluation").__file__))
        self.assertEqual(source_file("review.py"), Path(import_module("benchmarks.calibration.review").__file__))
        # Saved assessments locate the repository before importing the package.
        sentinel = PROJECT_ROOT / "benchmarks/calibration/common.py"
        self.assertTrue(sentinel.is_file())
        self.assertEqual(sentinel.resolve(), PROJECT_ROOT / "benchmarks/calibration/engine/common.py")

    def test_annotation_command_passes_help_to_selected_tool(self):
        with redirect_stdout(io.StringIO()) as output, self.assertRaises(SystemExit) as exited:
            main(["annotations", "extract", "--help"])
        self.assertEqual(exited.exception.code, 0)
        self.assertIn("--selection", output.getvalue())
        self.assertIn("--output", output.getvalue())


if __name__ == "__main__":
    unittest.main()
