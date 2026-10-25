"""Valida els límits entre CSV extern, observacions originals i mesures de tracking."""

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from trampoline_vision.contracts.observations import VideoAsset
from trampoline_vision.ingestion.errors import InputError
from trampoline_vision.ingestion.manifest import CaseManifest
from trampoline_vision.ingestion.recorded_boxes import iter_box_frames
from trampoline_vision.preparation.config import PreparationConfig
from trampoline_vision.preparation.pipeline import prepare_frame


class BoxIngestionTests(unittest.TestCase):
    """Evita falses poses, identitats derivades de det_id i buits interpretats implícitament."""

    def setUp(self):
        """Crea només dades sintètiques, sense dependre del repositori TFM."""
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.csv = root / 'boxes.csv'
        self.video = VideoAsset('case', root/'video.mp4', 96, 64, 30, (0., 1/30, 2/30), (1/30,)*3)
        self.manifest = CaseManifest(root/'manifest.json', 'case', self.video.path, self.csv, 0,
                                    'test', 'original', {}, None, (), 'person_boxes_csv', 'complete_video')

    def frames(self, rows, **kwargs):
        """Executa el lector real fins al final per capturar errors també després de l'últim frame."""
        self.csv.write_text('frame,det_id,x1,y1,x2,y2,conf,class_id\n' + rows, encoding='utf-8')
        return list(iter_box_frames(self.manifest, self.video, **kwargs))

    def test_boxes_preserve_raw_confidence_without_fake_joints(self):
        """La preparació de caixes no exigeix confiança ni articulacions pròpies d'OpenPose."""
        frames = self.frames('0,2,5,5,20,45,0.001,0\n0,0,35,5,50,45,0.9,0\n')
        prepared = prepare_frame(frames[0], PreparationConfig())
        self.assertEqual([d.provenance.source_person_index for d in frames[0].detections], [0, 2])
        self.assertEqual([c.measurement.score for c in prepared.candidates], [.9, .001])
        self.assertTrue(all(d.keypoints == () and d.skeleton_schema is None for d in frames[0].detections))
        self.assertTrue(all(c.measurement.source == 'detector' for c in prepared.candidates))
        self.assertEqual(frames[1].source_status, 'present')
        self.assertEqual(frames[1].detections, ())

    def test_coverage_and_external_index_base_are_explicit(self):
        """Una fila absent pot ser negatiu o manca de dades; la base externa no desplaça el vídeo."""
        self.manifest = replace(self.manifest, frame_index_base=1, frame_coverage='listed_frames_only')
        frames = self.frames('1,0,5,5,20,45,0.9,0\n')
        self.assertEqual(frames[0].detections[0].provenance.source_frame_index, 1)
        self.assertEqual(frames[1].source_status, 'missing')
        with self.assertRaisesRegex(InputError, 'Missing recorded'):
            self.frames('1,0,5,5,20,45,0.9,0\n', missing_frames_policy='error')

    def test_invalid_records_fail_with_source_context(self):
        """Rebutja duplicats, ordre temporal, geometria, scores i classes alienes a persones."""
        rows = ['0,0,5,5,20,45,.9,0\n0,0,5,5,20,45,.9,0\n',
                '1,0,5,5,20,45,.9,0\n0,0,5,5,20,45,.9,0\n',
                '3,0,5,5,20,45,.9,0\n', '0,0,-1,5,20,45,.9,0\n',
                '0,0,5,5,20,45,nan,0\n', '0,0,5,5,20,45,.9,1\n',
                '0,0,5,5,5,45,.9,0\n']
        for row in rows:
            with self.subTest(row=row), self.assertRaises(InputError):
                self.frames(row)
