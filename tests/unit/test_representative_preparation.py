"""Checks the opt-in silhouette path without YOLO or a tracking backend."""

from importlib import util
import json
import unittest

from trampoline_vision.contracts.geometry import BoundingBox
from trampoline_vision.contracts.observations import DetectionProvenance, FrameContext, FrameDetections, PersonBoxDetection
from trampoline_vision.preparation.config import BoxPreparationPolicy, PreparationConfig, RepresentativeBoxPolicy
from trampoline_vision.preparation.pipeline import prepare_frame, prepare_frames
from trampoline_vision.results.preparation import preparation_record


def source(boxes, scores):
    detections = tuple(
        PersonBoxDetection(str(i), BoundingBox(*box), score,
                           DetectionProvenance("recorded.csv", f"csv_line:{i+2}", 0, i, "test", "original"))
        for i, (box, score) in enumerate(zip(boxes, scores, strict=True))
    )
    return FrameDetections(FrameContext("video", 0, 0., .04, 320, 240), detections, "present")


@unittest.skipUnless(util.find_spec("cv2") and util.find_spec("numpy"), "Silhouette preparation dependencies required")
class RepresentativePreparationTests(unittest.TestCase):
    def test_omitted_zone_mode_keeps_exterior_boxes_eligible(self):
        """El valor per defecte soft conserva una caixa exterior si hi ha pressupost."""
        from trampoline_vision.preparation.representative import RepresentativeBoxPreparer
        _, _, image = self.prepared("hard", 12)
        default = PreparationConfig.from_dict({"schema_version": "1.0", "box_preparation": {"enabled": True},
            "representative_boxes": {"zone": [.25, .15, .75, .85]}})
        self.assertEqual(default.representative_boxes.zone_mode, "soft")
        preparer = RepresentativeBoxPreparer("video", default, [image])
        result = preparer.prepare(source([(20, 60, 70, 170)], [.8]), image)
        self.assertEqual(len(result.candidates), 1)

    def test_audit_keeps_absorption_after_budget_is_full(self):
        """El tall no impedeix absorbir una duplicada posterior ni altera la geometria activa."""
        import numpy as np
        from trampoline_vision.preparation.foreground import rank_regions_with_audit
        from trampoline_vision.preparation.regions import Region
        image = np.zeros((240, 320, 3), dtype=np.uint8)
        regions = (Region(0, "a", .9, (0,), (110, 70, 180, 170), 0, .9),
                   Region(1, "b", .5, (1,), (220, 70, 280, 170), 1, .5),
                   Region(2, "c", .1, (2,), (112, 72, 178, 168), 2, .1))
        active, decisions = rank_regions_with_audit(regions, image, image[::2, ::2],
            np.asarray((0, 0, 320, 240)), hard_zone=False, limit=1)
        self.assertEqual([entry.reason for entry in decisions],
                         ["selected", "candidate_limit", "absorbed_containment"])
        self.assertEqual(decisions[-1].selected_anchor_source_id, "a")
        self.assertEqual(active[0].members, (0, 2))
        self.assertEqual(active[0].bbox, regions[0].bbox)

    def test_audit_explains_zone_and_limit_without_losing_originals(self):
        """Contrasta exclusions reals i serialització, sense confondre rànquing i confiança."""
        frame = source([(20, 60, 70, 170), (110, 75, 145, 150), (165, 75, 203, 150)], [.8, .6, .5])
        for mode, expected in (("hard", {"selected", "outside_hard_zone", "candidate_limit"}),
                               ("soft", {"selected", "candidate_limit"})):
            config, preparer, image = self.prepared(mode, 1)
            result = preparer.prepare_with_audit(frame, image)
            self.assertEqual({entry.reason for entry in result.selections}, expected)
            self.assertEqual((result.source_count, result.grouped_count, result.region_count), (3, 3, 3))
            self.assertEqual({ref for entry in result.selections for ref in entry.source_detection_ids}, {"0", "1", "2"})
            record = json.loads(json.dumps(preparation_record(result.frame, config, audit=result), allow_nan=False))
            self.assertEqual(record["selection_audit"]["selected_count"], 1)
            self.assertEqual(len(record["source"]["detections"]), 3)
            with self.assertRaisesRegex(ValueError, "belong"):
                preparation_record(preparer.prepare(frame, image), config, audit=result)

    def prepared(self, mode, cap):
        import numpy as np
        from trampoline_vision.preparation.representative import RepresentativeBoxPreparer
        config = PreparationConfig(box_preparation=BoxPreparationPolicy(enabled=True),
                                   representative_boxes=RepresentativeBoxPolicy((.25, .15, .75, .85), cap, mode))
        background = np.zeros((240, 320, 3), dtype=np.uint8)
        return config, RepresentativeBoxPreparer("video", config, [background]), background.copy()

    def test_hard_and_soft_zone_and_cap_preserve_all_sources(self):
        hard_config, hard, image = self.prepared("hard", 2)
        soft_config, soft, _ = self.prepared("soft", 2)
        image[60:170, 30:90] = 255
        # Make the bright box unambiguously outside the 80-pixel zone.
        frame = source([(20, 60, 70, 170), (110, 75, 145, 150), (165, 75, 203, 150)], [.8, .6, .5])
        inside = prepare_frame(frame, hard_config, representative=hard, image=image)
        allowed = prepare_frame(frame, soft_config, representative=soft, image=image)
        self.assertEqual({c.source_detection_ids[0] for c in inside.candidates}, {"1", "2"})
        self.assertEqual(allowed.candidates[0].source_detection_ids, ("0",))
        self.assertEqual(allowed.candidates[0].measurement.score, .8)
        self.assertEqual(len(allowed.candidates), 2)
        self.assertIs(allowed.source, frame)
        self.assertEqual(len(preparation_record(allowed, soft_config)["source"]["detections"]), 3)

    def test_weak_spatial_extent_has_seed_score_and_its_own_origin(self):
        config, preparer, background = self.prepared("hard", 12)
        frame = source([(110, 83, 165, 155), (125, 83, 180, 155), (111, 96, 167, 169),
                        (123, 72, 178, 145)], [.06, .04, .03, .02])
        result = list(prepare_frames([frame], config, representative=preparer, images=[background]))[0]
        self.assertEqual(len(result.candidates), 1)
        candidate = result.candidates[0]
        self.assertEqual(candidate.measurement.source, "support_extent")
        self.assertEqual(candidate.measurement.score, .06)
        self.assertEqual(candidate.measurement.bbox, BoundingBox(110, 72, 180, 169))
        self.assertEqual(set(candidate.source_detection_ids), {"0", "1", "2", "3"})
        with self.assertRaisesRegex(ValueError, "matching fitted preparer"):
            prepare_frame(frame, config)
