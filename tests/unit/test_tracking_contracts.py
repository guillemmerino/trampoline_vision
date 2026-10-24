"""Proves de les fronteres de tracking, sense biblioteca externa ni vídeos reals.

Protegeixen la procedència, els candidats parcials, l'assignació unívoca i la
distinció entre mesura i predicció. No proven cap algoritme d'associació.
"""

from dataclasses import FrozenInstanceError, replace
import unittest

from trampoline_vision.contracts.observations import (
    BODY25_NAMES, DetectionProvenance, FrameContext, FrameDetections,
    KeypointObservation, PersonDetection,
)
from trampoline_vision.contracts.tracking import (
    BoundingBox, BoxMeasurement, TrackSample, TrackingCandidate,
    TrackingFrame, TrackingFrameResult,
)


def source_frame(timestamp=0.2, status="present", ids=("1:0", "1:1")):
    """Crea observacions febles a zero píxels per comprovar que no s'alterin ni es filtrin."""
    points = tuple(KeypointObservation(n, 0.0, 0.0, 0.05, True, True) for n in BODY25_NAMES)
    provenance = DetectionProvenance("poses.zip", "frame_2.json", 2, 0, "fused", "unknown")
    detections = tuple(PersonDetection(i, points, provenance) for i in ids)
    return FrameDetections(FrameContext("case", 1, timestamp, 0.04, 100, 80), detections, status)


def measured_candidate(candidate_id="c0", refs=("1:0",), score=0.05):
    """Construeix una extensió de pose petita, sense afirmar que sigui una caixa de cos complet."""
    measurement = BoxMeasurement(BoundingBox(0, 0, 10, 20), "pose_extent", score, "synthetic_v1")
    return TrackingCandidate(candidate_id, refs, measurement)


class TrackingContractTests(unittest.TestCase):
    """Comprova les invariants que els futurs preparadors i adaptadors hauran de respectar."""

    def test_invalid_geometry_and_scores_are_rejected(self):
        """Evita NaN, infinits, booleans, rectangles degenerats i indicadors fora de rang."""
        for coordinates in [(0, 0, 0, 3), (3, 0, 1, 3), (0, 2, 3, 2),
                            (False, 0, 3, 3), (0, 0, float("inf"), 3),
                            (float("nan"), 0, 3, 3), ("0", 0, 3, 3)]:
            with self.subTest(coordinates=coordinates), self.assertRaises(ValueError):
                BoundingBox(*coordinates)
        for score in [-0.01, 1.01, True, float("nan"), float("inf"), None]:
            with self.subTest(score=score), self.assertRaises(ValueError):
                measured_candidate(score=score)

    def test_zero_score_and_outside_box_are_preserved(self):
        """No converteix zero en absència ni retalla geometria fora del fotograma."""
        candidate = measured_candidate(score=0)
        box = BoundingBox(-5, -10, 120, 90)
        measurement = replace(candidate.measurement, bbox=box)
        self.assertEqual(measurement.score, 0)
        self.assertEqual(measurement.bbox.x_min, -5)

    def test_measurement_requires_explicit_origin_and_score_method(self):
        """Una caixa predita o un score sense semàntica no són mesures d'entrada."""
        measurement = measured_candidate().measurement
        for changes in [{"source": "predicted"}, {"score_method": " "}, {"bbox": None}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(measurement, **changes)

    def test_partial_and_grouped_candidates_preserve_original_source(self):
        """Agrupar referències o conservar una pose sense caixa no modifica les articulacions febles."""
        source = source_frame()
        grouped = TrackingFrame(source, (measured_candidate(refs=("1:0", "1:1")),))
        partial = TrackingCandidate("partial", ("1:0",), None, ("insufficient_spatial_support",))
        frame = TrackingFrame(source, (partial,))
        result = TrackingFrameResult(frame, (), ("partial",))
        self.assertIs(grouped.source, source)
        self.assertIs(result.frame.source, source)
        self.assertEqual(len(source.detections), 2)
        self.assertEqual(source.detections[0].keypoints[0].confidence, 0.05)
        self.assertEqual(source.detections[0].keypoints[0].x, 0)

    def test_candidate_references_and_immutability(self):
        """Rebutja fonts inventades, reutilitzacions i col·leccions que es podrien mutar."""
        candidate = measured_candidate()
        for changes in [{"source_detection_ids": ()}, {"source_detection_ids": ("1:0", "1:0")},
                        {"source_detection_ids": ["1:0"]}, {"issues": ["partial"]},
                        {"measurement": None}, {"candidate_id": ""}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(candidate, **changes)
        for candidates in [(measured_candidate(refs=("unknown",)),),
                           (candidate, measured_candidate("c1")), (candidate, candidate), [candidate]]:
            with self.subTest(candidates=candidates), self.assertRaises(ValueError):
                TrackingFrame(source_frame(), candidates)
        with self.assertRaises(FrozenInstanceError):
            candidate.candidate_id = "changed"

    def test_observed_assignment_and_prediction_are_distinct(self):
        """Permet una identitat observada i una de perduda, sense fabricar nova evidència."""
        frame = TrackingFrame(source_frame(), (measured_candidate(), measured_candidate("c1", ("1:1",))))
        observed = TrackSample("ocsort:0", "active", "observed", frame.candidates[0].measurement.bbox, "c0", 0.2)
        predicted = TrackSample("ocsort:1", "lost", "predicted", BoundingBox(2, 3, 12, 23), None, 0.1)
        result = TrackingFrameResult(frame, (observed, predicted), ("c1",))
        self.assertEqual(result.tracks[0].track_id, "ocsort:0")
        self.assertIsNone(result.tracks[1].candidate_id)
        self.assertEqual(result.tracks[1].last_observed_timestamp_s, 0.1)

    def test_invalid_track_evidence_and_states(self):
        """Impedeix prediccions amb candidat actual i estats observats sense mesura."""
        observed = TrackSample("id", "active", "observed", BoundingBox(0, 0, 1, 1), "c0", 0.2)
        for changes in [{"track_id": " "}, {"state": "unknown"}, {"state": "lost"},
                        {"state": "finished"}, {"bbox": None}, {"candidate_id": None},
                        {"evidence": "predicted"}, {"last_observed_timestamp_s": -1},
                        {"last_observed_timestamp_s": True}, {"last_observed_timestamp_s": float("nan")}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(observed, **changes)

    def test_result_rejects_ambiguous_or_invented_assignments(self):
        """Una detecció no pot alimentar dues identitats ni desaparèixer de la partició de candidats."""
        candidate = measured_candidate()
        frame = TrackingFrame(source_frame(), (candidate,))
        observed = TrackSample("id", "active", "observed", candidate.measurement.bbox, "c0", 0.2)
        cases = [((observed, replace(observed, track_id="other")), ()),
                 ((observed, observed), ()), ((observed,), ("c0",)),
                 ((), ()), ((), ("unknown",)), ((), ("c0", "c0")),
                 ((replace(observed, candidate_id="unknown"),), ()),
                 ((replace(observed, bbox=BoundingBox(1, 1, 11, 21)),), ()),
                 ((replace(observed, last_observed_timestamp_s=0.1),), ())]
        for tracks, unassigned in cases:
            with self.subTest(tracks=tracks, unassigned=unassigned), self.assertRaises(ValueError):
                TrackingFrameResult(frame, tracks, unassigned)

    def test_partial_candidate_cannot_be_reported_as_box_observation(self):
        """Conservar una pose parcial no autoritza inventar una caixa observada per al tracker."""
        partial = TrackingCandidate("p", ("1:0",), None, ("partial",))
        frame = TrackingFrame(source_frame(), (partial,))
        sample = TrackSample("id", "active", "observed", BoundingBox(0, 0, 1, 1), "p", 0.2)
        with self.assertRaisesRegex(ValueError, "measured candidate"):
            TrackingFrameResult(frame, (sample,), ())

    def test_empty_and_missing_frames_keep_time_and_allow_only_past_predictions(self):
        """Un JSON buit i un JSON absent mantenen el temps però no creen observacions actuals."""
        for status in ("present", "missing"):
            frame = TrackingFrame(source_frame(status=status, ids=()), ())
            predicted = TrackSample("id", "lost", "predicted", None, None, 0.1)
            result = TrackingFrameResult(frame, (predicted,), ())
            self.assertEqual(result.frame.source.source_status, status)
            self.assertEqual(result.frame.source.context.timestamp_s, 0.2)
            for time in (0.2, 0.3):
                with self.subTest(status=status, time=time), self.assertRaises(ValueError):
                    TrackingFrameResult(frame, (replace(predicted, last_observed_timestamp_s=time),), ())
