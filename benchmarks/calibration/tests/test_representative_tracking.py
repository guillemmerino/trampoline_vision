"""Regression for rendering visible tracking evidence at annotated discrepancies."""

from importlib import util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from benchmarks.calibration.tools.representative_tracking import VARIANTS, review_image


@unittest.skipUnless(util.find_spec('numpy') and util.find_spec('PIL'), 'Overlay dependencies required')
class RepresentativeReviewTests(unittest.TestCase):
    def test_visible_reference_draws_observed_and_predicted_track_boxes(self):
        import numpy as np
        from PIL import Image

        image = np.zeros((160, 200, 3), dtype='uint8')
        target = [20, 25, 120, 145]
        tracks = {'hard12': [
            {'track_id': 'bytetrack:1', 'state': 'active', 'evidence': 'observed',
             'bbox': [28, 32, 118, 137]},
            {'track_id': 'bytetrack:2', 'state': 'lost', 'evidence': 'predicted',
             'bbox': [35, 40, 105, 127]},
        ]}
        with TemporaryDirectory() as temp:
            dest = Path(temp) / 'review.jpg'
            review_image(image, target, target, {variant: [] for variant in VARIANTS},
                         tracks, dest, [0, 0, 195, 158])
            with Image.open(dest) as output:
                # hard12 is the first panel of the second row.
                row_y = (160 + 22) + 22
                green = output.getpixel((28, row_y + 85))
                magenta = output.getpixel((35, row_y + 85))
                self.assertGreater(green[1], green[0] + 40)
                self.assertGreater(magenta[0], magenta[1] + 40)
