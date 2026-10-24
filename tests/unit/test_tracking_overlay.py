"""Proves de dibuix d'identitats observades i estimades sense alterar imatge ni observacions."""

from dataclasses import replace
import importlib.util
import unittest

from helpers_tracking import tracking_frame
from trampoline_vision.contracts.tracking import TrackSample, TrackingFrameResult
from trampoline_vision.results.overlay import HEADER_HEIGHT, RenderStyle
from trampoline_vision.results.tracking import TrackingOverlayFrame, render_tracking_frame, track_color


@unittest.skipUnless(importlib.util.find_spec("PIL"), "Pillow visualization extra required")
class TrackingOverlayTests(unittest.TestCase):
    """Diferencia evidència observada/predita i comprova independència dels filtres visuals."""

    def test_predictions_have_no_observed_keypoints_and_color_is_stable(self):
        """Una caixa predita conserva ID/color però no dibuixa les articulacions de l'últim instant."""
        from PIL import Image

        frame = tracking_frame(1, .1)
        candidate = frame.candidates[0]
        observed = TrackSample("ocsort:0", "active", "observed", candidate.measurement.bbox, candidate.candidate_id, .1)
        result = TrackingFrameResult(frame, (observed,), ())
        image = Image.new("RGB", (64, 48), "black")
        before = image.tobytes()
        style = RenderStyle(view="all", min_confidence=0, min_visible_points=1)
        rendered, counts = render_tracking_frame(image, TrackingOverlayFrame(result), style)
        self.assertGreater(counts["tracking"]["keypoints_drawn"], 0)
        self.assertEqual(rendered.size, (64, 48 + HEADER_HEIGHT))
        self.assertEqual(rendered.getpixel((32, 6 + HEADER_HEIGHT)), track_color("ocsort:0"))
        predicted = replace(observed, state="lost", evidence="predicted", candidate_id=None, last_observed_timestamp_s=0)
        result = TrackingFrameResult(frame, (predicted,), (candidate.candidate_id,))
        rendered, counts = render_tracking_frame(image, TrackingOverlayFrame(result), style)
        self.assertEqual(counts["tracking"]["keypoints_drawn"], 0)
        self.assertEqual(counts["tracking"]["predicted_tracks"], 1)
        self.assertEqual(rendered.getpixel((32, 6 + HEADER_HEIGHT)), (0, 0, 0))
        self.assertEqual(image.tobytes(), before)

    def test_pose_display_filter_does_not_hide_track_box(self):
        """Un filtre de dibuix exigent amaga punts, però no elimina la identitat ni la caixa associada."""
        from PIL import Image

        frame = tracking_frame()
        candidate = frame.candidates[0]
        sample = TrackSample("id", "active", "observed", candidate.measurement.bbox, candidate.candidate_id, 0)
        result = TrackingFrameResult(frame, (sample,), ())
        _, counts = render_tracking_frame(Image.new("RGB", (64, 48)), TrackingOverlayFrame(result),
                                           RenderStyle(view="all", min_confidence=.99))
        self.assertEqual(counts["tracking"]["observed_tracks"], 1)
        self.assertEqual(counts["tracking"]["keypoints_drawn"], 0)
