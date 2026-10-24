"""Proves del dibuix que contrasten píxels, filtres i preservació de les observacions."""

import importlib.util
import unittest

from trampoline_vision.contracts.observations import (
    BODY25_NAMES, DetectionProvenance, FrameContext, FrameDetections, KeypointObservation, PersonDetection,
)
from trampoline_vision.results.errors import VisualizationError
from trampoline_vision.results.overlay import HEADER_HEIGHT, RenderStyle, render_frame


def observed_frame(width=64, height=48):
    """Crea una aresta visible i un punt de baixa confiança per contrastar les dues vistes."""
    points = [KeypointObservation(name, None, None, 0, False, None) for name in BODY25_NAMES]
    for index, x, confidence in [(2, 20, .9), (3, 40, .9), (4, 50, .1)]:
        points[index] = KeypointObservation(BODY25_NAMES[index], x, 20, confidence, True, True)
    person = PersonDetection("0:0", tuple(points), DetectionProvenance("poses.zip", "frame_000001_keypoints.json", 1, 0, "recorded", "unknown"))
    return FrameDetections(FrameContext("test", 0, 0, .2, width, height), (person,), "present")


@unittest.skipUnless(importlib.util.find_spec("PIL"), "Pillow visualization extra is not installed")
class OverlayTests(unittest.TestCase):
    """Comprova geometria del dibuix i semàntica exclusivament visual dels llindars."""

    def test_edge_geometry_and_source_are_preserved(self):
        """L'aresta apareix a les coordenades originals més la capçalera, sense alterar la imatge d'entrada."""
        from PIL import Image
        source = Image.new("RGB", (64, 48), "white")
        observations = observed_frame()
        rendered, stats = render_frame(source, observations, RenderStyle(min_confidence=.5, min_visible_points=2, show_labels=False))
        self.assertNotEqual(rendered.getpixel((30, 20 + HEADER_HEIGHT)), (255, 255, 255))
        self.assertEqual(source.getpixel((30, 20)), (255, 255, 255))
        self.assertEqual(stats["filtered"]["keypoints_drawn"], 2)
        self.assertEqual(stats["filtered"]["edges_drawn"], 1)
        self.assertEqual(observations.detections[0].keypoints[4].confidence, .1)

    def test_comparison_panels_apply_only_visual_filters(self):
        """El punt feble es veu a all i desapareix a filtered, mantenint escala i desplaçament declarats."""
        from PIL import Image
        rendered, stats = render_frame(Image.new("RGB", (64, 48), "white"), observed_frame(),
                                       RenderStyle(view="compare", min_confidence=.5, min_visible_points=2, show_labels=False))
        self.assertEqual(rendered.size, (128, 112))
        self.assertNotEqual(rendered.getpixel((50, 84)), (255, 255, 255))
        self.assertEqual(rendered.getpixel((114, 84)), (255, 255, 255))
        self.assertEqual(stats["all"]["keypoints_drawn"], 3)
        self.assertEqual(stats["filtered"]["keypoints_drawn"], 2)

    def test_minimum_points_hides_detection_without_changing_input(self):
        """El mínim de punts amaga només el dibuix, no elimina la detecció del contracte."""
        from PIL import Image
        observations = observed_frame()
        _, stats = render_frame(Image.new("RGB", (64, 48)), observations, RenderStyle(min_visible_points=3))
        self.assertEqual(stats["filtered"]["detections_drawn"], 0)
        self.assertEqual(len(observations.detections), 1)

    def test_empty_frame_and_odd_dimensions_keep_image(self):
        """Un buit conserva imatge i temps; el padding per codificar no deforma píxels."""
        from PIL import Image
        context = FrameContext("test", 0, 0, .2, 63, 47)
        empty = FrameDetections(context, (), "missing")
        rendered, stats = render_frame(Image.new("RGB", (63, 47), (7, 8, 9)), empty, RenderStyle())
        self.assertEqual(rendered.size, (64, 112))
        self.assertEqual(rendered.getpixel((20, 84)), (7, 8, 9))
        self.assertEqual(stats["filtered"]["detections_drawn"], 0)

    def test_zero_coordinate_and_outside_point_are_distinguished(self):
        """Un punt al marge es dibuixa; un punt fora de la imatge no es desplaça artificialment."""
        from PIL import Image
        points = [KeypointObservation(name, None, None, 0, False, None) for name in BODY25_NAMES]
        points[0] = KeypointObservation("nose", 0, 0, .9, True, True)
        points[1] = KeypointObservation("neck", 100, 10, .9, True, False)
        person = PersonDetection("0:0", tuple(points), observed_frame().detections[0].provenance)
        frame = FrameDetections(observed_frame().context, (person,), "present")
        image, counts = render_frame(Image.new("RGB", (64, 48), "white"), frame, RenderStyle(view="all", show_labels=False))
        self.assertNotEqual(image.getpixel((0, HEADER_HEIGHT)), (255, 255, 255))
        self.assertEqual(counts["all"]["keypoints_drawn"], 1)
        self.assertEqual(counts["all"]["edges_drawn"], 0)

    def test_wrong_dimensions_are_rejected(self):
        """Evita dibuixar dades d'un vídeo sobre una imatge amb una altra geometria."""
        from PIL import Image
        with self.assertRaises(VisualizationError):
            render_frame(Image.new("RGB", (65, 48)), observed_frame(), RenderStyle())


class StyleTests(unittest.TestCase):
    """Valida opcions sense necessitar biblioteques de dibuix o vídeo."""

    def test_invalid_options_are_rejected(self):
        """Rebutja llindars fora de rang, valors ambigus i opcions desconegudes."""
        for settings in [{"view": "tracking"}, {"view": []}, {"min_confidence": float("nan")},
                         {"min_confidence": True}, {"min_visible_points": 0},
                         {"min_visible_points": 26}, {"show_labels": "false"}]:
            with self.subTest(settings=settings), self.assertRaises(VisualizationError):
                RenderStyle(**settings)
