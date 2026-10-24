"""Proves sintètiques de caixes, confiança i agrupació, sense inferència ni vídeo real.

Els casos representen poses febles, invertides, parcials i persones properes.
Són comprovacions geomètriques controlades, no un benchmark de precisió.
"""

from dataclasses import asdict, replace
import unittest

from trampoline_vision.contracts.observations import (
    BODY25_NAMES, DetectionProvenance, FrameContext, FrameDetections,
    KeypointObservation, PersonDetection,
)
from trampoline_vision.preparation.config import DeduplicationPolicy, PoseBoxPolicy, PreparationConfig
from trampoline_vision.preparation.pipeline import prepare_frame, prepare_frames


_POSE = {
    "neck": (50, 25), "right_shoulder": (40, 30), "left_shoulder": (60, 30),
    "mid_hip": (50, 50), "right_knee": (45, 65), "left_knee": (55, 65),
    "right_ankle": (43, 80), "left_ankle": (57, 80),
}  # Pose vertical simplificada amb suport al tronc i les cames.


def detection(identifier="a", coordinates=None, confidence=0.1):
    """Construeix BODY_25 amb absències explícites i procedència diferent per detecció."""
    coordinates = _POSE if coordinates is None else coordinates
    points = []
    for name in BODY25_NAMES:
        if name in coordinates:
            x, y = coordinates[name]
            inside = 0 <= x < 200 and 0 <= y < 150
            points.append(KeypointObservation(name, x, y, confidence, True, inside))
        else:
            points.append(KeypointObservation(name, None, None, 0, False, None))
    provenance = DetectionProvenance("synthetic.zip", f"{identifier}.json", 1, 0, "synthetic", "unknown")
    return PersonDetection(identifier, tuple(points), provenance)


def frame(*detections, status="present", index=0, timestamp=0.0):
    """Crea un fotograma de dimensions fixes amb temps explícit i zero o més persones."""
    return FrameDetections(FrameContext("case", index, timestamp, 0.04, 200, 150), tuple(detections), status)


def shifted(dx, dy=0):
    """Trasllada tota la pose sense canviar-ne els noms ni la forma."""
    return {name: (x + dx, y + dy) for name, (x, y) in _POSE.items()}


class PreparationTests(unittest.TestCase):
    """Protegeix les decisions que poden perdre evidència o fusionar persones erròniament."""

    def test_weak_pose_keeps_original_points_and_explicit_score(self):
        """Una pose amb confiança 0.03 pot aportar caixa sense aplicar el filtre visual 0.25."""
        source = frame(detection(confidence=0.03))
        result = prepare_frame(source)
        candidate = result.candidates[0]
        self.assertIs(result.source, source)
        self.assertEqual(candidate.source_detection_ids, ("a",))
        self.assertAlmostEqual(candidate.measurement.score, 0.03)
        self.assertEqual(candidate.measurement.score_method, "selected_keypoint_confidence_mean_v1")
        self.assertEqual(candidate.measurement.source, "pose_extent")
        self.assertIn("pose_extent_only", candidate.issues)
        self.assertEqual(candidate.measurement.bbox.x_min, 39)
        self.assertAlmostEqual(candidate.measurement.bbox.y_max, 82.75)
        self.assertEqual(source.detections[0].keypoints[1].confidence, 0.03)

    def test_empty_and_partial_poses_are_kept_with_reasons(self):
        """Absència, braços sols i punts col·lapsats no es converteixen en caixes artificials."""
        cases = [({}, "insufficient_points"),
                 ({"right_elbow": (20, 20), "left_elbow": (30, 25),
                   "right_wrist": (10, 30), "left_wrist": (40, 35)}, "insufficient_anatomical_support"),
                 ({name: (50, 50) for name in _POSE}, "insufficient_spatial_support")]
        for coordinates, issue in cases:
            with self.subTest(issue=issue):
                source = frame(detection(coordinates=coordinates))
                candidate = prepare_frame(source).candidates[0]
                self.assertIsNone(candidate.measurement)
                self.assertIn(issue, candidate.issues)
                self.assertEqual(candidate.source_detection_ids, ("a",))

    def test_support_thresholds_are_applied_before_padding(self):
        """Un marge gran no pot rescatar una pose d'un sol punt o amb amplada zero."""
        policy = PoseBoxPolicy(padding_ratio=1, min_span_px=0, min_span_image_ratio=0)
        coordinates = {name: (20, y) for name, (_, y) in _POSE.items()}
        candidate = prepare_frame(frame(detection(coordinates=coordinates)), PreparationConfig(box=policy)).candidates[0]
        self.assertIsNone(candidate.measurement)
        self.assertIn("insufficient_spatial_support", candidate.issues)

    def test_resolution_relative_minimum_rejects_spatial_noise(self):
        """Molts punts dins d'una regió ínfima no esdevenen una persona mesurable pel recompte."""
        coordinates = {name: (50 + x / 1000, 50 + y / 1000) for name, (x, y) in _POSE.items()}
        config = PreparationConfig(box=PoseBoxPolicy(min_span_px=0, min_span_image_ratio=0.002))
        candidate = prepare_frame(frame(detection(coordinates=coordinates)), config).candidates[0]
        self.assertIsNone(candidate.measurement)
        self.assertIn("insufficient_spatial_support", candidate.issues)

    def test_confidence_configuration_does_not_destroy_raw_data(self):
        """Augmentar el llindar només deixa sense mesura el candidat, mantenint l'observació original."""
        source = frame(detection(confidence=0.1))
        config = PreparationConfig(box=PoseBoxPolicy(min_keypoint_confidence=0.2))
        result = prepare_frame(source, config)
        self.assertIsNone(result.candidates[0].measurement)
        self.assertIn("points_below_preparation_threshold", result.candidates[0].issues)
        self.assertIs(result.source.detections[0], source.detections[0])

    def test_score_uses_selected_mean_and_confidence_boundary_is_inclusive(self):
        """La mitjana usa tots els punts seleccionats i excloure un punt feble canvia l'indicador explícitament."""
        person = detection(confidence=0.9)
        person = replace(person, keypoints=tuple(replace(p, confidence=0.1) if p.name == "neck" else p
                                                 for p in person.keypoints))
        source = frame(person)
        inclusive = PreparationConfig(box=PoseBoxPolicy(min_keypoint_confidence=0.1))
        above = PreparationConfig(box=PoseBoxPolicy(min_keypoint_confidence=0.1001))
        first = prepare_frame(source, inclusive).candidates[0]
        second = prepare_frame(source, above).candidates[0]
        self.assertAlmostEqual(first.measurement.score, 0.8)
        self.assertAlmostEqual(second.measurement.score, 0.9)
        self.assertLess(first.measurement.bbox.y_min, second.measurement.bbox.y_min)
        self.assertNotIn("points_below_preparation_threshold", first.issues)
        self.assertIn("points_below_preparation_threshold", second.issues)

    def test_border_zero_outside_and_padding_have_distinct_semantics(self):
        """Zero continua sent observat, els punts externs no amplien la caixa i el padding no es retalla."""
        coordinates = {"neck": (0, 0), "right_shoulder": (10, 0), "mid_hip": (5, 10),
                       "right_knee": (5, 20), "left_ankle": (-1000, 1000)}
        candidate = prepare_frame(frame(detection(coordinates=coordinates))).candidates[0]
        self.assertEqual(candidate.measurement.bbox.x_min, -0.5)
        self.assertEqual(candidate.measurement.bbox.y_min, -1)
        self.assertEqual(candidate.measurement.bbox.y_max, 21)
        self.assertIn("points_outside_frame", candidate.issues)

    def test_inverted_and_horizontal_poses_do_not_require_upright_aspect_ratio(self):
        """Les mateixes articulacions continuen donant caixa cap per avall o girades 90 graus."""
        poses = [{name: (100 - x, 120 - y) for name, (x, y) in _POSE.items()},
                 {name: (y, x) for name, (x, y) in _POSE.items()}]
        for coordinates in poses:
            with self.subTest(coordinates=coordinates):
                self.assertIsNotNone(prepare_frame(frame(detection(coordinates=coordinates))).candidates[0].measurement)

    def test_deduplication_is_opt_in(self):
        """La configuració inicial no amaga propostes, encara que siguin geomètricament idèntiques."""
        source = frame(detection("a"), detection("b"))
        self.assertEqual(len(prepare_frame(source).candidates), 2)

    def test_duplicate_comparison_scales_with_pose_size(self):
        """La mateixa pertorbació relativa dona el mateix grup en una pose petita i una de més gran."""
        config = PreparationConfig(deduplication=DeduplicationPolicy(enabled=True))
        for scale in (0.25, 1):
            first = {n: (x * scale, y * scale) for n, (x, y) in _POSE.items()}
            second = {n: ((x + 1) * scale, y * scale) for n, (x, y) in _POSE.items()}
            with self.subTest(scale=scale):
                result = prepare_frame(frame(detection("a", first), detection("b", second)), config)
                self.assertEqual(len(result.candidates), 1)

    def test_grouping_retains_best_whole_measurement_without_score_inflation(self):
        """Dues poses duplicades creen un candidat, preservant totes dues fonts i la millor mesura."""
        source = frame(detection("low", confidence=0.05), detection("high", shifted(0.1), 0.2))
        config = PreparationConfig(deduplication=DeduplicationPolicy(enabled=True))
        result = prepare_frame(source, config)
        self.assertEqual(len(result.candidates), 1)
        candidate = result.candidates[0]
        self.assertEqual(candidate.source_detection_ids, ("high", "low"))
        self.assertAlmostEqual(candidate.measurement.score, 0.2)
        self.assertAlmostEqual(candidate.measurement.bbox.x_min, 39.1)
        self.assertIn("duplicates_grouped", candidate.issues)
        self.assertEqual(len(result.source.detections), 2)

    def test_fuller_representative_precedes_higher_confidence_fragment(self):
        """El representant es tria primer per suport, evitant substituir una pose més completa per quatre punts forts."""
        fragment = {n: _POSE[n] for n in ("neck", "right_shoulder", "left_shoulder", "mid_hip", "right_knee", "right_ankle")}
        source = frame(detection("full", confidence=0.05), detection("fragment", fragment, 0.9))
        config = PreparationConfig(deduplication=DeduplicationPolicy(enabled=True, min_box_iou=0.5))
        candidate = prepare_frame(source, config).candidates[0]
        self.assertEqual(candidate.source_detection_ids, ("full", "fragment"))
        self.assertAlmostEqual(candidate.measurement.score, 0.05)

    def test_overlapping_people_with_different_joints_stay_separate(self):
        """Igual caixa no basta: articulacions internes desplaçades impedeixen agrupar dues persones."""
        altered = dict(_POSE, mid_hip=(40, 30))
        config = PreparationConfig(deduplication=DeduplicationPolicy(enabled=True))
        result = prepare_frame(frame(detection("a"), detection("b", altered)), config)
        self.assertEqual(len(result.candidates), 2)

    def test_partial_and_disjoint_evidence_cannot_be_absorbed(self):
        """Una pose sense caixa i una sense prou punts compartits continuen com a candidats independents."""
        partial = {"right_wrist": (50, 40)}
        disjoint = {"left_elbow": (40, 25), "right_elbow": (60, 80),
                    "left_wrist": (50, 60), "left_hip": (50, 50)}
        config = PreparationConfig(deduplication=DeduplicationPolicy(enabled=True))
        result = prepare_frame(frame(detection("a"), detection("p", partial), detection("b", disjoint)), config)
        self.assertEqual(len(result.candidates), 3)
        self.assertEqual(sum(c.measurement is None for c in result.candidates), 1)

    def test_complete_link_prevents_chain_merges(self):
        """A~B i B~C no autoritzen agrupar A i C si les seves articulacions són massa llunyanes."""
        config = PreparationConfig(deduplication=DeduplicationPolicy(enabled=True))
        result = prepare_frame(frame(detection("a"), detection("b", shifted(3)), detection("c", shifted(6))), config)
        self.assertEqual([c.source_detection_ids for c in result.candidates], [("a", "b"), ("c",)])

    def test_grouping_is_deterministic_and_partitions_every_source(self):
        """Reordenar l'entrada no canvia agrupació, IDs ni mesures, i cada font figura exactament una vegada."""
        inputs = (detection("c", shifted(40)), detection("b", shifted(0.1)), detection("a"),
                  detection("partial", {}))
        config = PreparationConfig(deduplication=DeduplicationPolicy(enabled=True))
        first = prepare_frame(frame(*inputs), config)
        second = prepare_frame(frame(*reversed(inputs)), config)
        self.assertEqual(first.candidates, second.candidates)
        refs = [r for c in first.candidates for r in c.source_detection_ids]
        self.assertCountEqual(refs, [d.detection_id for d in inputs])
        self.assertEqual(len(refs), len(set(refs)))

    def test_empty_missing_and_irregular_times_survive_lazy_stream(self):
        """No salta instants ni consumeix anticipadament un stream, encara que no hi hagi candidats."""
        visited = []

        def sources():
            """Registra el consum per comprovar mandra i preserva un buit intermedi sense JSON."""
            for i, timestamp in enumerate((0.0, 0.07, 0.2)):
                visited.append(i)
                yield frame(status="missing" if i == 1 else "present", index=i, timestamp=timestamp)

        prepared = prepare_frames(sources())
        self.assertEqual(visited, [])
        first = next(prepared)
        self.assertEqual(visited, [0])
        output = [first, *prepared]
        self.assertEqual([p.source.context.timestamp_s for p in output], [0, 0.07, 0.2])
        self.assertEqual(output[1].source.source_status, "missing")
        self.assertTrue(all(p.candidates == () for p in output))


class PreparationConfigTests(unittest.TestCase):
    """Valida els límits configurables i impedeix ignorar errors de noms o tipus."""

    def test_strict_config_and_effective_defaults(self):
        """L'objecte parcial resol defaults i rebutja versions desconegudes, booleans numèrics i claus errònies."""
        config = PreparationConfig.from_dict({"schema_version": "1.0", "box": {"min_points": 5}})
        self.assertEqual(config.box.min_points, 5)
        self.assertFalse(asdict(config)["deduplication"]["enabled"])
        cases = [{}, {"schema_version": "2.0"}, {"schema_version": "1.0", "render": {}},
                 {"schema_version": "1.0", "box": {"min_point": 4}},
                 {"schema_version": "1.0", "box": None},
                 {"schema_version": "1.0", "box": {"min_points": True}},
                 {"schema_version": "1.0", "box": {"min_keypoint_confidence": float("nan")}},
                 {"schema_version": "1.0", "deduplication": {"enabled": "false"}}]
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ValueError):
                PreparationConfig.from_dict(value)

    def test_policy_ranges_reject_invalid_limits(self):
        """Evita comptatges impossibles, llindars negatius i marges no finits abans de processar dades."""
        for changes in [{"min_points": 1}, {"min_points": 26}, {"require_core": 1},
                        {"min_anatomical_groups": 0}, {"min_span_px": -1},
                        {"min_span_image_ratio": 2}, {"padding_ratio": float("inf")},
                        {"min_keypoint_confidence": True}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(PoseBoxPolicy(), **changes)
        for changes in [{"min_shared_points": 0}, {"min_box_iou": 2},
                        {"max_point_distance_ratio": -0.1}, {"enabled": 1}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(DeduplicationPolicy(), **changes)
