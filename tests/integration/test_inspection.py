"""Proves del recorregut de lectura, informe, exportació i CLI.

La majoria injecta temps sintètics per aïllar l'orquestració. Una prova
genera un MP4 amb FFmpeg i consulta ffprobe realment; s'omet si aquestes
eines no són al PATH i s'executa dins de la imatge Docker de tests.
"""

from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from helpers import body25, make_case, timeline
from trampoline_vision.application.inspection import inspect_case
from trampoline_vision.ingestion.manifest import load_manifest
from trampoline_vision.ingestion.video import probe_video
from trampoline_vision.interfaces.cli.main import main


class InspectionTests(unittest.TestCase):
    """Comprova la coherència entre dades llegides, artefactes i resultat de la comanda."""
    def setUp(self):
        """Prepara un cas amb un fotograma buit, un absent i un amb una persona, tot temporal."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = make_case(self.root, {
            "frame_000001_keypoints.json": {"people": []},
            "frame_000003_keypoints.json": {"people": [{"pose_keypoints_2d": body25()}]},
        })

    def test_counts_provenance_gap_and_jsonl(self):
        """Comprova recomptes, avisos de durada, procedència i exportació d'un registre per fotograma."""
        obj = json.loads(self.path.read_text())
        obj["reference_metadata"] = {"declared_duration_s": 25}
        self.path.write_text(json.dumps(obj))
        output = io.StringIO()
        result = inspect_case(load_manifest(self.path), timeline(self.root), frames_output=output)
        self.assertEqual(result["counts"]["frames"], 3)
        self.assertEqual(result["counts"]["empty_present_frames"], 1)
        self.assertEqual(result["counts"]["missing_source_records"], 1)
        self.assertEqual(result["counts"]["valid_observed_keypoints"], 25)
        self.assertIn("reference_duration_mismatch", [w["code"] for w in result["warnings"]])
        lines = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(lines[1]["source_status"], "missing")
        self.assertEqual(lines[-1]["detections"][0]["provenance"]["source_frame_index"], 3)
        self.assertNotIn("track_id", lines[-1]["detections"][0])

    def test_cli_publishes_only_after_complete_read_and_refuses_overwrite(self):
        """Verifica una sortida correcta i que repetir el nom no alteri l'informe anterior."""
        output = self.root / "summary.json"
        with patch("trampoline_vision.interfaces.cli.main.probe_video", return_value=timeline(self.root)):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["inspect", "--manifest", str(self.path), "--output", str(output)]), 0)
                original = output.read_bytes()
                self.assertEqual(main(["inspect", "--manifest", str(self.path), "--output", str(output)]), 2)
            self.assertEqual(output.read_bytes(), original)

    def test_failed_read_does_not_publish_outputs(self):
        """Exigeix que un JSON corrupte no publiqui informe ni exportació com si la lectura fos completa."""
        self.path = make_case(self.root, {"frame_000001_keypoints.json": "malformed"})
        output, frames = self.root / "summary.json", self.root / "frames.jsonl"
        with patch("trampoline_vision.interfaces.cli.main.probe_video", return_value=timeline(self.root)):
            with redirect_stderr(io.StringIO()):
                code = main(["inspect", "--manifest", str(self.path), "--output", str(output), "--frames-output", str(frames)])
        self.assertEqual(code, 2)
        self.assertFalse(output.exists())
        self.assertFalse(frames.exists())

    # A Docker les eines existeixen i aquesta prova s’executa; localment l’omissió queda informada.
    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg/ffprobe not on PATH; Docker test image includes both")
    def test_real_video_probe_and_cli(self):
        """Genera un MP4 de tres fotogrames i prova dimensions, durada i CLI amb ffprobe real.

        Aquesta prova contrasta també les hipòtesis sobre el format que retorna
        FFmpeg, en lloc de confiar només en respostes simulades.
        """
        video = self.root / "video.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x48:r=5:d=0.6",
                        "-c:v", "mpeg4", str(video)], check=True, timeout=30, capture_output=True)
        asset = probe_video(video, "test-case")
        self.assertEqual(asset.frame_count, 3)
        self.assertEqual((asset.width_px, asset.height_px), (64, 48))
        self.assertAlmostEqual(asset.duration_s, 0.6, places=5)
        output = self.root / "summary.json"
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["inspect", "--manifest", str(self.path), "--output", str(output)]), 0)
        self.assertEqual(json.loads(output.read_text())["counts"]["frames"], 3)
