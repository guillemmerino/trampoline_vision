"""Perfils substituïbles, rutes relatives i evidència forta/feble sense carregar models."""

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from helpers_boxes import box_frame, appearance
from trampoline_vision.contracts.appearance import FrameAppearance
from trampoline_vision.ingestion.errors import ManifestError
from trampoline_vision.ingestion.tracking_config import load_tracking_config
from trampoline_vision.perception.appearance.config import AppearanceConfig
from trampoline_vision.tracking.backend import BackendUpdate
from trampoline_vision.tracking.config import TrackerConfig
from trampoline_vision.tracking.errors import TrackingError
from trampoline_vision.tracking.session import TrackingSession


class TrackerProfileTests(unittest.TestCase):
    """Verifica configuració estricta i polítiques comunes de vida abans de mutar el backend."""

    def test_backend_parameters_are_not_silently_ignored(self):
        """Un perfil no pot contenir opcions d'un altre tracker ni habilitar ReID on no es consumeix."""
        for value in [dict(schema_version='2.0', backend='bytetrack', parameters={'direction_weight': .2}),
                      dict(schema_version='2.0', backend='botsort', lifecycle={'max_lost': 10}),
                      dict(schema_version='2.0', backend='unknown'),
                      dict(schema_version='2.0', backend='ocsort', appearance=dict(provider='osnet', weights='/weights', sha256='0'*64))]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                TrackerConfig.from_dict(value)

    def test_referenced_paths_resolve_from_each_declaring_file(self):
        """El pipeline, el perfil i el model tenen bases de ruta pròpies; llegir-los no extreu aparença."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'profiles').mkdir()
            (root/'models').mkdir()
            (root/'models/weights.pt').write_bytes(b'fixture')
            model = dict(schema_version='1.0', provider='osnet', weights='weights.pt', sha256='0'*64, cache_dir='../cache')
            (root/'models/model.json').write_text(json.dumps(model))
            profile = dict(schema_version='2.0', backend='botsort', appearance={'model_config': '../models/model.json'})
            (root/'profiles/profile.json').write_text(json.dumps(profile))
            pipeline = dict(schema_version='2.0', task='track_recorded_detections', case_manifest='case.json', tracker_config='profiles/profile.json')
            path = root/'pipeline.json'
            path.write_text(json.dumps(pipeline))
            config = load_tracking_config(path)
            self.assertEqual(config.tracker.appearance.weights, str((root/'models/weights.pt').resolve()))
            self.assertEqual(config.tracker.appearance.cache_dir, str((root/'cache').resolve()))
            self.assertIn((root/'models/model.json').resolve(), config.protected_paths)
            pipeline['tracker'] = {}
            path.write_text(json.dumps(pipeline))
            with self.assertRaisesRegex(ManifestError, 'not both'):
                load_tracking_config(path)

    def test_weak_evidence_keeps_confirmed_id_but_resets_birth_streak(self):
        """Una associació feble serveix per mantenir; els naixements exigeixen ratxa de mesures fortes."""
        backend = Mock(requires_appearance=False)
        session = TrackingSession(TrackerConfig(confirmation_frames=2), 30, backend=backend)
        for index, score in enumerate((.9, .05, .9, .9, .05)):
            frame = box_frame(index, (0,), score)
            candidate = frame.candidates[0]
            backend.update.return_value = BackendUpdate(((candidate.candidate_id, 0),), ((0, candidate.measurement.bbox),))
            result = session.update(frame)
            self.assertEqual(len(result.tracks), 1 if index >= 3 else 0)
        self.assertEqual(result.tracks[0].evidence, 'observed')
        self.assertEqual(result.tracks[0].last_observed_timestamp_s, 4/30)

    def test_invalid_appearance_fails_before_backend_mutation(self):
        """Context, candidats i model han de coincidir; un error de dades es pot corregir sense reiniciar la sessió."""
        backend = Mock(requires_appearance=True)
        config = TrackerConfig(backend='botsort', appearance=AppearanceConfig('osnet', '/weights', '0'*64))
        session = TrackingSession(config, 30, backend=backend)
        frame = box_frame(0, (0,))
        for vectors in (None, appearance(box_frame(1, (0,))), FrameAppearance(frame.source.context, 'synthetic', ())):
            with self.assertRaises(TrackingError):
                session.update(frame, vectors)
        backend.update.assert_not_called()
        candidate = frame.candidates[0]
        backend.update.return_value = BackendUpdate(((candidate.candidate_id, 0),), ((0, candidate.measurement.bbox),))
        session.update(frame, appearance(frame))
        frame = box_frame(1, (0,))
        with self.assertRaisesRegex(TrackingError, 'model changed'):
            session.update(frame, appearance(frame, 'different-model'))
        self.assertEqual(backend.update.call_count, 1)
