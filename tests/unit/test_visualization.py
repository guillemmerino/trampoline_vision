"""Proves de selecció temporal i contrast de la sortida, sense codecs ni GPU."""

from dataclasses import replace
from pathlib import Path
import unittest

from helpers import timeline
from trampoline_vision.application.visualization import select_frame_range, validate_rendered_video
from trampoline_vision.results.errors import VisualizationError
from trampoline_vision.results.overlay import RenderStyle


class VisualizationTimelineTests(unittest.TestCase):
    """Protegeix límits exclusius, últim fotograma i detecció de desfasaments de recodificació."""

    def test_interval_selects_presentation_starts(self):
        """El límit final és exclusiu i l'interval complet conserva el darrer fotograma."""
        source = timeline(Path("."))
        self.assertEqual(select_frame_range(source, 0, None), (0, 3))
        self.assertEqual(select_frame_range(source, .2, .4), (1, 2))

    def test_invalid_or_empty_interval_is_rejected(self):
        """No s'accepten intervals fora del vídeo ni intervals sense cap inici de fotograma."""
        source = timeline(Path("."))
        for start, end in [(-1, .2), (0, 1), (.4, .2), (.01, .1), (float("nan"), .2)]:
            with self.subTest(start=start, end=end), self.assertRaises(VisualizationError):
                select_frame_range(source, start, end)

    def test_output_count_geometry_and_times_are_checked(self):
        """Un vídeo de la mateixa durada però amb fotogrames perduts o moguts no passa la validació."""
        source = timeline(Path("."))
        good = replace(source, height_px=144)
        self.assertTrue(validate_rendered_video(source, good, 0, 3, RenderStyle())["timestamps_verified"])
        bad_outputs = [replace(good, timestamps_s=(0, .2), frame_durations_s=(.2, .2)),
                       replace(good, timestamps_s=(0, .21, .4)), replace(good, width_px=101),
                       replace(good, frame_durations_s=(.2, .2, .3))]
        for output in bad_outputs:
            with self.subTest(output=output), self.assertRaises(VisualizationError):
                validate_rendered_video(source, output, 0, 3, RenderStyle())
