"""Checks the opt-in silhouette path without YOLO or a tracking backend."""

from importlib import util
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
