"""Proves de conversió temporal i errors de ffprobe sense eines externes.

Injecten el JSON del sondeig per comprovar temps variables, normalització
d'origen i errors de captura que podrien desalinear les deteccions.
"""

from pathlib import Path
import unittest
from unittest.mock import patch

from trampoline_vision.ingestion.errors import VideoProbeError
from trampoline_vision.ingestion.video import probe_video, video_from_probe


def probe(times=(3.0, 3.04, 3.12), last_duration="0.06"):
    """Genera una resposta ffprobe sintètica amb temps i última durada configurables.

    Permet provocar timestamps duplicats, vídeo buit o durada final absent
    sense generar fitxers de vídeo ni executar un subprocess.
    """
    frames = [{"best_effort_timestamp_time": str(t), "width": 100, "height": 80} for t in times]
    if frames and last_duration is not None:
        frames[-1]["pkt_duration_time"] = last_duration
    return {"streams": [{"width": 100, "height": 80, "avg_frame_rate": "25/1"}], "frames": frames}


class VideoTests(unittest.TestCase):
    """Comprova que la línia temporal vingui dels temps i que les ambigüitats es declarin."""
    def test_variable_timing_and_nonzero_source_origin(self):
        """Verifica intervals variables i origen extern no nul, sense substituir-los per FPS constants."""
        video = video_from_probe(probe(), Path("video.mp4"), "video")
        self.assertEqual(video.source_start_s, 3)
        self.assertAlmostEqual(video.timestamps_s[2], 0.12)
        self.assertAlmostEqual(video.frame_durations_s[1], 0.08)
        self.assertAlmostEqual(video.duration_s, 0.18)

    def test_missing_last_duration_is_marked_as_estimated(self):
        """Exigeix un avís quan s'aproxima la durada de l'últim fotograma."""
        video = video_from_probe(probe(last_duration=None), Path("video.mp4"), "video")
        self.assertIn("last_frame_duration_estimated_from_timestamp_deltas", video.warnings)

    def test_non_increasing_or_missing_timestamps_are_errors(self):
        """Rebutja temps absents o no creixents i vídeos sense fotogrames."""
        for data in [probe((0, 0)), probe((0.1, 0)), {"streams": probe()["streams"], "frames": [{}]}, probe(())]:
            with self.subTest(data=data), self.assertRaises(VideoProbeError):
                video_from_probe(data, Path("video.mp4"), "video")

    def test_rotation_and_variable_dimensions_are_rejected(self):
        """Evita acceptar geometria que necessitaria una transformació addicional de les poses."""
        rotated = probe()
        rotated["streams"][0]["side_data_list"] = [{"rotation": 90}]
        variable = probe()
        variable["frames"][-1]["width"] = 99
        for data in [rotated, variable]:
            with self.subTest(data=data), self.assertRaises(VideoProbeError):
                video_from_probe(data, Path("video.mp4"), "video")

    def test_missing_binary_has_actionable_error(self):
        """Comprova que l'absència de ffprobe indiqui Docker o instal·lació com a solució."""
        with patch("trampoline_vision.ingestion.video.subprocess.run", side_effect=FileNotFoundError):
            with self.assertRaisesRegex(VideoProbeError, "Docker CPU"):
                probe_video(Path("video.mp4"), "video")
