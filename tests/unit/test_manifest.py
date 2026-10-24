"""Proves del manifest i de la configuració executable d'inspecció.

Verifiquen rutes independents del directori actual i declaracions
explícites d'esquema, índex i coordenades, sense inferències silencioses.
"""

import json
from pathlib import Path
import tempfile
import unittest

from helpers import make_case
from trampoline_vision.ingestion.errors import ManifestError
from trampoline_vision.ingestion.manifest import load_inspection_config, load_manifest


class ManifestTests(unittest.TestCase):
    """Exercita validació de fonts i separació entre disseny i configuració executable."""
    def setUp(self):
        """Crea un cas aïllat i programa la neteja de tots els fitxers temporals.

        resolve unifica també rutes llargues i curtes de Windows en les comparacions.
        """
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.path = make_case(self.root, {"frame_000001_keypoints.json": {"people": []}})

    def test_paths_resolve_from_manifest_not_current_directory(self):
        """Comprova que vídeo i ZIP es busquin al costat del manifest, no de la CLI."""
        manifest = load_manifest(self.path)
        self.assertEqual(manifest.video_path, self.root / "video.mp4")
        self.assertEqual(manifest.detections_path, self.root / "poses.zip")

    def test_semantics_are_not_guessed(self):
        """Rebutja índexs ambigus, espais de coordenades i formats que el lector no implementa."""
        for field, value in [("frame_index_base", True), ("frame_index_base", 2),
                             ("coordinate_space", "crop_pixels"), ("skeleton_schema", "coco17"),
                             ("format", "legacy_openpose_csv")]:
            with self.subTest(field=field):
                obj = json.loads(self.path.read_text())
                obj["detections"]["primary"][field] = value
                altered = self.root / "altered.json"
                altered.write_text(json.dumps(obj))
                with self.assertRaises(ManifestError):
                    load_manifest(altered)

    def test_design_only_pipeline_is_not_executed(self):
        """Evita retornar èxit sobre un pipeline que només documenta funcionalitats futures."""
        path = self.root / "pipeline.json"
        path.write_text(json.dumps({"schema_version": "0.1-draft", "implementation_status": "design-only"}))
        with self.assertRaisesRegex(ManifestError, "Unknown|design-only"):
            load_inspection_config(path)

    def test_executable_config_resolves_manifest_and_policy(self):
        """Comprova que la configuració resolgui el manifest relatiu i conservi la política de buits."""
        folder = self.root / "config"
        folder.mkdir()
        path = folder / "inspect.json"
        path.write_text(json.dumps({"schema_version": "1.0", "task": "inspect_recorded_detections",
                                    "case_manifest": "../case.json", "missing_frames_policy": "error"}))
        self.assertEqual(load_inspection_config(path), (self.path, "error"))
