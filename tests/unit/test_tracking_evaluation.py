"""Proves d'anotacions disperses: èxits observats, canvis d'ID i errors de referència."""

import json
from contextlib import redirect_stdout, redirect_stderr
import io
from pathlib import Path
import tempfile
import unittest

from helpers_tracking import tracking_frame
from trampoline_vision.application.tracking_evaluation import evaluate_tracking
from trampoline_vision.contracts.tracking import TrackSample, TrackingFrameResult
from trampoline_vision.results.tracking import tracking_record
from trampoline_vision.tracking.config import TrackerConfig
from trampoline_vision.tracking.errors import TrackingError
from trampoline_vision.interfaces.cli.main import main
from trampoline_vision.preparation.config import PreparationConfig, DeduplicationPolicy
from trampoline_vision.preparation.pipeline import prepare_frame


class TrackingEvaluationTests(unittest.TestCase):
    """No compta caixes predites com observacions i exigeix coherència entre anotacions i exportació."""

    def setUp(self):
        """Prepara fitxers petits independents per cada prova."""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.tracks = self.root / "tracks.jsonl"
        self.annotations = self.root / "annotations.json"

    def record(self, index, track_id=None):
        """Crea un registre vàlid amb una observació assignada o un candidat sense assignar."""
        frame = tracking_frame(index, index * .1)
        candidate = frame.candidates[0]
        sample = (TrackSample(track_id, "active", "observed", candidate.measurement.bbox,
                              candidate.candidate_id, index * .1),) if track_id else ()
        result = TrackingFrameResult(frame, sample, () if track_id else (candidate.candidate_id,))
        return {**tracking_record(result, (), TrackerConfig()), "run_id": "run"}

    def write(self, records, samples, **kwargs):
        """Desa registres i anotacions manuals d'un mateix vídeo sintètic."""
        self.tracks.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        annotation = {"schema_version": "1.0", "video_id": "test-case", "samples": samples, **kwargs}
        self.annotations.write_text(json.dumps(annotation), encoding="utf-8")

    def test_sparse_matches_id_changes_and_missing_evidence(self):
        """Un canvi després d'una absència es registra, mentre la cobertura només usa mesures assignades."""
        records = [self.record(0, "ocsort:0"), self.record(1), self.record(2, "ocsort:1")]
        samples = [{"frame_index": i, "subject_id": "gymnast", "source_detection_id": "a"} for i in range(3)]
        self.write(records, samples)
        result = evaluate_tracking(self.tracks, self.annotations)
        self.assertEqual(result["observed_matches"], 2)
        self.assertEqual(result["unmatched_samples"], 1)
        self.assertAlmostEqual(result["observed_coverage_on_annotations"], 2 / 3)
        self.assertEqual(len(result["observed_id_changes"]), 1)
        self.assertEqual(result["observed_id_changes"][0]["previous_frame"], 0)
        self.assertEqual(result["subjects"]["gymnast"]["track_ids"], ["ocsort:0", "ocsort:1"])

    def test_null_detection_means_unobserved_and_unknown_reference_is_error(self):
        """Permet anotar una persona visible sense proposta; un ID escrit incorrectament no es compta com miss."""
        self.write([self.record(0)], [{"frame_index": 0, "subject_id": "g", "source_detection_id": None}])
        self.assertEqual(evaluate_tracking(self.tracks, self.annotations)["observed_matches"], 0)
        self.write([self.record(0)], [{"frame_index": 0, "subject_id": "g", "source_detection_id": "typo"}])
        with self.assertRaisesRegex(TrackingError, "unknown detection"):
            evaluate_tracking(self.tracks, self.annotations)

    def test_outside_duplicate_or_wrong_video_annotations_fail(self):
        """No retorna mètriques sobre un altre clip, una anotació duplicada o un instant no exportat."""
        sample = {"frame_index": 0, "subject_id": "g", "source_detection_id": "a"}
        for samples, options in [([sample, sample], {}), ([sample], {"video_id": "other"}),
                                 ([{**sample, "frame_index": 3}], {})]:
            self.write([self.record(0)], samples, **options)
            with self.subTest(samples=samples, options=options), self.assertRaises(TrackingError):
                evaluate_tracking(self.tracks, self.annotations)

    def test_mixed_or_repeated_export_frames_fail(self):
        """Una exportació concatenada o corrupta no pot produir diagnòstics aparentment vàlids."""
        sample = {"frame_index": 0, "subject_id": "g", "source_detection_id": "a"}
        for records in [[self.record(0), self.record(0)], [self.record(0), {**self.record(1), "run_id": "other"}]]:
            self.write(records, [sample])
            with self.assertRaises(TrackingError):
                evaluate_tracking(self.tracks, self.annotations)

    def test_merged_subjects_are_explicit_even_if_both_sources_were_assigned(self):
        """Una agrupació errònia de dues persones no es considera bona només perquè cobreix totes dues fonts."""
        frame = prepare_frame(tracking_frame(people=("a", "b")).source,
                              PreparationConfig(deduplication=DeduplicationPolicy(enabled=True)))
        candidate = frame.candidates[0]
        sample = TrackSample("ocsort:0", "active", "observed", candidate.measurement.bbox, candidate.candidate_id, 0)
        record = {**tracking_record(TrackingFrameResult(frame, (sample,), ()), (), TrackerConfig()), "run_id": "run"}
        samples = [{"frame_index": 0, "subject_id": person, "source_detection_id": person} for person in ("a", "b")]
        self.write([record], samples)
        result = evaluate_tracking(self.tracks, self.annotations)
        self.assertEqual(result["observed_matches"], 2)
        self.assertEqual(len(result["merged_subjects"]), 1)
        self.assertEqual(result["merged_subjects"][0]["subject_ids"], ["a", "b"])

    def test_evaluation_cli_publishes_and_refuses_overwrite(self):
        """La revisió és executable sense extres i no sobreescriu una valoració prèvia."""
        self.write([self.record(0, "ocsort:0")], [{"frame_index": 0, "subject_id": "g", "source_detection_id": "a"}])
        output = self.root / "evaluation.json"
        args = ["evaluate-tracking", "--tracks", str(self.tracks), "--annotations", str(self.annotations), "--output", str(output)]
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(main(args), 0)
            before = output.read_bytes()
            self.assertEqual(main(args), 2)
        self.assertEqual(output.read_bytes(), before)
        self.assertEqual(json.loads(before)["observed_matches"], 1)
