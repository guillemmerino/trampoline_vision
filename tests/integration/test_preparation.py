"""Comprovació del recorregut lector OpenPose -> preparació amb registres sintètics.

Valida la frontera real d'ingestió sense descarregar models ni obrir vídeos de TFM.
"""

from pathlib import Path
import tempfile
import unittest

from helpers import make_case, timeline
from trampoline_vision.ingestion.json_io import read_json
from trampoline_vision.ingestion.manifest import load_manifest
from trampoline_vision.ingestion.openpose import iter_openpose_frames
from trampoline_vision.preparation.config import PreparationConfig
from trampoline_vision.preparation.pipeline import prepare_frames


class PreparationIntegrationTests(unittest.TestCase):
    """Exercita dades llegides i configuració del repositori sense reemplaçar la font original."""

    def test_reader_stream_and_repository_config(self):
        """Preserva confiança baixa, índex extern, registre absent i fotograma final al nou límit."""
        config_path = Path(__file__).resolve().parents[2] / "configs/preparation/pose-candidates.json"
        # Al contenidor les configuracions viuen al directori de treball del paquet instal·lat.
        if not config_path.exists():
            config_path = Path("configs/preparation/pose-candidates.json")
        config = PreparationConfig.from_dict(read_json(config_path))
        values = [0.0] * 75
        for index, (x, y) in {1: (50, 10), 2: (40, 20), 5: (60, 20), 8: (50, 40), 10: (45, 60)}.items():
            values[index * 3:index * 3 + 3] = [x, y, 0.03]
        person = {"pose_keypoints_2d": values}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = make_case(root, {"frame_000001_keypoints.json": {"people": [person, person]},
                                    "frame_000003_keypoints.json": {"people": []}})
            frames = list(prepare_frames(iter_openpose_frames(load_manifest(path), timeline(root)), config))
        self.assertEqual(len(frames), 3)
        self.assertEqual(len(frames[0].candidates), 2)
        self.assertAlmostEqual(frames[0].candidates[0].measurement.score, 0.03)
        self.assertEqual(frames[0].source.detections[0].provenance.source_frame_index, 1)
        self.assertEqual(frames[1].source.source_status, "missing")
        self.assertEqual(frames[1].source.context.timestamp_s, 0.2)
        self.assertEqual(frames[2].source.source_status, "present")
        self.assertEqual(frames[2].candidates, ())
