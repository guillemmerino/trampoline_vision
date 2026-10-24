"""Proves de lectura OpenPose amb JSON i línia temporal sintètics.

Reprodueixen errors sensibles del prototip: perdre dades al final,
confondre zero amb absència i saltar-se fotogrames sense deteccions.
No requereixen GPU, FFmpeg ni vídeos originals.
"""

import json
from pathlib import Path
import tempfile
import unittest

from helpers import body25, make_case, timeline
from trampoline_vision.ingestion.errors import DetectionFormatError
from trampoline_vision.ingestion.manifest import load_manifest
from trampoline_vision.ingestion.openpose import iter_openpose_frames


class OpenPoseTests(unittest.TestCase):
    """Valida ordre, semàntica dels punts i errors de registres de detecció."""
    def setUp(self):
        """Prepara una carpeta temporal exclusiva i n'assegura la neteja després de cada cas."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def frames(self, records, **kwargs):
        """Construeix la font de prova i en consumeix el generador amb una línia temporal de tres fotogrames."""
        path = make_case(self.root, records, **kwargs)
        return list(iter_openpose_frames(load_manifest(path), timeline(self.root)))

    def test_numeric_order_gap_and_final_frame(self):
        """Verifica ordre numèric, registre absent intermedi i conservació de l'últim fotograma."""
        frames = self.frames({"nested/frame_000003_keypoints.json": {"people": [{"pose_keypoints_2d": body25()}]},
                              "nested/frame_000001_keypoints.json": {"people": []}})
        self.assertEqual([f.context.frame_index for f in frames], [0, 1, 2])
        self.assertEqual([f.source_status for f in frames], ["present", "missing", "present"])
        self.assertEqual(len(frames[-1].detections), 1)
        self.assertAlmostEqual(frames[-1].context.timestamp_s, 0.4)
        self.assertEqual(frames[-1].detections[0].provenance.source_frame_index, 3)

    def test_all_detections_of_last_frame_are_preserved(self):
        """Protegeix contra la regressió que descartava l'última persona de l'últim fotograma."""
        person = {"pose_keypoints_2d": body25()}
        frames = self.frames({"frame_000003_keypoints.json": {"people": [person, person]}})
        self.assertEqual([d.detection_id for d in frames[-1].detections], ["2:0", "2:1"])

    def test_zero_coordinate_is_observed_and_zero_confidence_is_missing(self):
        """Separa un punt al marge (coordenada zero) d'un punt absent (confiança zero)."""
        values = body25(0, 0, 0.8)
        values[3:6] = [23, 44, 0]
        frames = self.frames({"frame_000001_keypoints.json": {"people": [{"pose_keypoints_2d": values}]}})
        points = frames[0].detections[0].keypoints
        self.assertTrue(points[0].valid)
        self.assertEqual((points[0].x, points[0].y), (0, 0))
        self.assertFalse(points[1].valid)
        self.assertIsNone(points[1].x)
        self.assertEqual(len(points), 25)

    def test_zero_based_directory_and_out_of_bounds_are_explicit(self):
        """Comprova carpeta zero-based i conservació de punts fora de la imatge sense retallar-los."""
        frames = self.frames({"clip_frame_000000_keypoints.json": {"people": [{"pose_keypoints_2d": body25(101, 5)}]}}, base=0, directory=True)
        point = frames[0].detections[0].keypoints[0]
        self.assertTrue(point.valid)
        self.assertFalse(point.in_frame)
        self.assertEqual(point.x, 101)

    def test_duplicate_indices_are_rejected_across_folders(self):
        """Rebutja dos JSON que afirmen descriure el mateix fotograma encara que siguin en carpetes diferents."""
        with self.assertRaisesRegex(DetectionFormatError, "Duplicate frame"):
            self.frames({"a/frame_000001_keypoints.json": {"people": []},
                         "b/frame_000001_keypoints.json": {"people": []}})

    def test_out_of_range_record_is_rejected(self):
        """Detecta registres que no corresponen a cap fotograma del vídeo associat."""
        with self.assertRaisesRegex(DetectionFormatError, "outside"):
            self.frames({"frame_000004_keypoints.json": {"people": []}})

    def test_malformed_and_nonfinite_records_are_errors_not_empty_frames(self):
        """Exigeix errors per JSON ambigu, formes incorrectes i nombres incompatibles, evitant buits falsos."""
        cases = ["{invalid", '{"people": [], "people": []}', '{"people": NaN}',
                 json.dumps({"people": [{"pose_keypoints_2d": [0] * 74}]}),
                 json.dumps({"people": [{"pose_keypoints_2d": body25(confidence=1.1)}]}),
                 json.dumps({"people": [{"pose_keypoints_2d": body25(x=True)}]})]
        for payload in cases:
            with self.subTest(payload=payload[:70]), self.assertRaises(DetectionFormatError):
                self.frames({"frame_000001_keypoints.json": payload})

    def test_missing_policy_error_and_empty_source(self):
        """Comprova que la política estricta rebutgi absències i que una font sense JSON no sembli vàlida."""
        path = make_case(self.root, {"frame_000001_keypoints.json": {"people": []}})
        with self.assertRaisesRegex(DetectionFormatError, "Missing 2"):
            list(iter_openpose_frames(load_manifest(path), timeline(self.root), missing_frames_policy="error"))
        with self.assertRaisesRegex(DetectionFormatError, "No JSON"):
            self.frames({})

    def test_unnamed_json_is_not_assigned_an_arbitrary_frame(self):
        """Evita inferir un fotograma d'un nom de fitxer que no segueix el patró declarat."""
        with self.assertRaisesRegex(DetectionFormatError, "Cannot parse"):
            self.frames({"unknown.json": {"people": []}})
