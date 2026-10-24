"""Recorreguts complets amb vídeos temporals, JSON, dibuix i sondeig independent."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from helpers import body25, make_case
from trampoline_vision.application.visualization import visualize_case
from trampoline_vision.ingestion.manifest import load_manifest
from trampoline_vision.ingestion.video import probe_video
from trampoline_vision.interfaces.cli.main import main
from trampoline_vision.results.errors import VisualizationError
from trampoline_vision.results.overlay import RenderStyle


@unittest.skipUnless(importlib.util.find_spec("av") and importlib.util.find_spec("PIL") and shutil.which("ffmpeg") and shutil.which("ffprobe"),
                     "Visualization extra and FFmpeg are required; Docker CPU includes them")
class VisualizationIntegrationTests(unittest.TestCase):
    """Contrasta que el MP4 final mantingui dades, temps i límits del cas seleccionat."""

    def setUp(self):
        """Genera un clip de tres fotogrames i registres amb un buit intermedi i dues deteccions finals."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.video = self.root / "video.mp4"
        self._make_video()
        person = {"pose_keypoints_2d": body25()}
        self.path = make_case(self.root, {"frame_000001_keypoints.json": {"people": []},
                                         "frame_000003_keypoints.json": {"people": [person, person]}})

    def _make_video(self, variable=False):
        """Crea MP4 via FFmpeg; el cas variable té inicis 0, 0.2 i 0.6 segons."""
        command = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x48:r=5:d=0.6"]
        if variable:
            command += ["-vf", "setpts='if(eq(N,0),0,if(eq(N,1),1,3))'", "-fps_mode", "vfr"]
        command += ["-c:v", "libx264", "-bf", "0", str(self.video)]
        subprocess.run(command, check=True, timeout=30, capture_output=True)

    def test_full_clip_keeps_empty_missing_and_last_frame(self):
        """El vídeo anotat conserva tres fotogrames i les dues deteccions de l'últim, també en comparació."""
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code = main(["visualize", "--manifest", str(self.path), "--output", str(self.root / "review.mp4"), "--view", "compare"])
        self.assertEqual(code, 0)
        report = json.loads((self.root / "review.json").read_text(encoding="utf-8"))
        self.assertEqual(report["output_video"]["frame_count"], 3)
        self.assertAlmostEqual(report["output_video"]["duration_s"], .6, places=4)
        self.assertEqual(report["output_video"]["width_px"], 128)
        self.assertEqual(report["frames"][1]["source_status"], "missing")
        self.assertEqual(report["frames"][-1]["source_detections"], 2)
        self.assertEqual(report["frames"][-1]["views"]["filtered"]["detections_drawn"], 2)
        self.assertEqual(report["validation"]["visual_alignment_status"], "pending_human_review")

    def test_partial_clip_resets_output_time_and_keeps_source_indices(self):
        """Un interval comença a zero al MP4 exportat i conserva els índexs i temps de la font a l'informe."""
        source = probe_video(self.video, "test-case")
        result = visualize_case(load_manifest(self.path), source, self.root / "part.mp4", self.root / "part.json", start_s=.2)
        self.assertEqual(result["range"]["first_frame_index"], 1)
        self.assertEqual(result["frames"][0]["timestamp_s"], .2)
        self.assertEqual(result["output_video"]["frame_count"], 2)
        self.assertAlmostEqual(result["output_video"]["duration_s"], .4, places=4)

    def test_variable_intervals_survive_encoding(self):
        """Contrasta timestamps irregulars amb ffprobe després de recodificar, sense forçar un vídeo CFR."""
        self._make_video(variable=True)
        source = probe_video(self.video, "test-case")
        self.assertAlmostEqual(source.timestamps_s[-1], .6, places=4)
        result = visualize_case(load_manifest(self.path), source, self.root / "vfr.mp4", self.root / "vfr.json")
        self.assertEqual(result["output_video"]["frame_count"], 3)
        self.assertLessEqual(result["validation"]["max_timestamp_error_s"], .0001)
        self.assertLessEqual(result["validation"]["duration_error_s"], .0001)

    def test_corrupt_record_does_not_publish_outputs(self):
        """Un error després de començar a codificar no publica un vídeo parcial com si fos complet."""
        path = make_case(self.root, {"frame_000001_keypoints.json": {"people": []}, "frame_000003_keypoints.json": "invalid"})
        with redirect_stderr(io.StringIO()):
            code = main(["visualize", "--manifest", str(path), "--output", str(self.root / "bad.mp4")])
        self.assertEqual(code, 2)
        self.assertFalse((self.root / "bad.mp4").exists())
        self.assertFalse((self.root / "bad.json").exists())

    def test_existing_video_is_preserved(self):
        """La visualització no sobreescriu un artefacte existent encara que el manifest sigui vàlid."""
        destination = self.root / "existing.mp4"
        destination.write_bytes(b"keep this")
        with self.assertRaises(VisualizationError):
            visualize_case(load_manifest(self.path), probe_video(self.video, "test-case"), destination, self.root / "new.json")
        self.assertEqual(destination.read_bytes(), b"keep this")
