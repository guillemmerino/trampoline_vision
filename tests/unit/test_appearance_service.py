"""Comprova que renderitzat i ReID comparteixen descodificació i que el cache evita inferència."""

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from helpers_boxes import box_frame, appearance
from trampoline_vision.application.appearance import AppearanceService
from trampoline_vision.contracts.observations import VideoAsset
from trampoline_vision.preparation.config import PreparationConfig


class AppearanceServiceTests(unittest.TestCase):
    """Usa un extractor controlat; la connexió SQLite i les claus d'entrada són les reals."""

    def test_shared_decode_then_cache_hit_does_not_load_model_or_pixels(self):
        """El segon replay reutilitza descriptors; el primer usa el frame ofert pel codificador."""
        frame = box_frame(0, (0,))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video_path, csv = root/'video.mp4', root/'boxes.csv'
            video_path.write_bytes(b'video fixture')
            csv.write_bytes(b'box fixture')
            video = VideoAsset('boxes', video_path, 96, 64, 30, (0.,), (1/30,))
            manifest = SimpleNamespace(detections_path=csv, detections_format='person_boxes_csv', frame_coverage='complete_video', frame_index_base=0)
            config = SimpleNamespace(cache_dir=str(root/'cache'))
            extractor = Mock(fingerprint='synthetic-osnet')
            extractor.extract.return_value = appearance(frame)
            decoded = Mock()
            with patch('trampoline_vision.application.appearance.OSNetExtractor', return_value=extractor), patch('trampoline_vision.application.appearance.validate_decoded'), patch('trampoline_vision.application.appearance.VideoFrameReader') as reader:
                service = AppearanceService(config, video, manifest, PreparationConfig())
                service.supply_decoded(0, decoded)
                self.assertEqual(service.for_frame(frame), appearance(frame))
                reader.return_value.get.assert_not_called()
                extractor.extract.assert_called_once_with(frame, decoded.to_ndarray.return_value)
                service.close()
                extractor.extract.reset_mock()
                decoded.to_ndarray.reset_mock()
                service = AppearanceService(config, video, manifest, PreparationConfig())
                self.assertEqual(service.for_frame(frame), appearance(frame))
                extractor.extract.assert_not_called()
                decoded.to_ndarray.assert_not_called()
                reader.return_value.get.assert_not_called()
                self.assertEqual(service.hits, 1)
                service.close()
