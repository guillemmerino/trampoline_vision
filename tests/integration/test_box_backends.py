"""Proves dels tres adaptadors reals amb caixes i aparença sintètiques, sense models externs."""

from importlib import util
from dataclasses import replace
import unittest

from helpers_boxes import box_frame, appearance
from trampoline_vision.perception.appearance.config import AppearanceConfig
from trampoline_vision.tracking.config import TrackerConfig
from trampoline_vision.tracking.session import TrackingSession
from trampoline_vision.tracking.errors import TrackingError


class BoxBackendTests(unittest.TestCase):
    """Comprova associació per candidat, recuperació i aïllament entre vídeos."""

    def exercise(self, backend, reid=False):
        """Canvia l'ordre de les deteccions i introdueix un buit curt sense canviar la identitat."""
        config = TrackerConfig(backend=backend, confirmation_frames=2,
            appearance=AppearanceConfig('osnet', '/unused/osnet_x0_25_msmt17.pt', '0'*64) if reid else None)
        session = TrackingSession(config, 30)
        last_mapping = None
        for index in range(8):
            frame = box_frame(index, () if index == 5 else ((1, 0) if index % 2 else (0, 1)))
            result = session.update(frame, appearance(frame) if reid else None)
            observed = [sample for sample in result.tracks if sample.evidence == 'observed']
            if index >= 3 and index != 5:
                mapping = {int(next(c.source_detection_ids[0] for c in frame.candidates if c.candidate_id == sample.candidate_id).split(':')[-1]): sample.track_id for sample in observed}
                self.assertEqual(len(mapping), 2)
                if last_mapping is not None:
                    self.assertEqual(mapping, last_mapping)
                last_mapping = mapping
            if index == 5:
                self.assertTrue(all(sample.state == 'lost' for sample in result.tracks))
        for index in range(8, 30):
            frame = box_frame(index, ())
            session.update(frame, appearance(frame) if reid else None)
        self.assertEqual(session.live, {})

    @unittest.skipUnless(util.find_spec('trackers'), 'Optional tracking extra is not installed')
    def test_ocsort_and_bytetrack(self):
        """Els dos trackers lleugers fan seguiment amb caixes sense carregar cap xarxa."""
        for name in ('ocsort', 'bytetrack'):
            with self.subTest(backend=name):
                self.exercise(name)

    @unittest.skipUnless(util.find_spec('boxmot'), 'Optional tracking-reid extra is not installed')
    def test_botsort_motion_and_external_reid(self):
        """BoT-SORT consumeix descriptors explícits; construir el backend no obre cap fitxer de pesos."""
        self.exercise('botsort')
        self.exercise('botsort', reid=True)

    @unittest.skipUnless(util.find_spec('boxmot'), 'Optional tracking-reid extra is not installed')
    def test_interleaved_sessions_have_independent_id_counters(self):
        """Crear i executar un altre vídeo no reinicia ni contamina els IDs del primer."""
        config = TrackerConfig(backend='botsort', confirmation_frames=1)
        first = TrackingSession(config, 30)
        first.update(box_frame())
        second = TrackingSession(config, 30)
        for index in range(1, 6):
            first.update(box_frame(index))
            second.update(box_frame(index-1))
        first_ids = set(first.live)
        second.update(box_frame(5, (0, 1, 2)))
        for index in range(6, 10):
            first.update(box_frame(index))
            second.update(box_frame(index, (0, 1, 2)))
        self.assertEqual(set(first.live), first_ids)
        self.assertEqual(len(first.live), 2)
        self.assertEqual(len(second.live), 3)

    @unittest.skipUnless(util.find_spec('boxmot'), 'Optional tracking-reid extra is not installed')
    def test_new_session_cannot_reuse_an_existing_id_in_another_video(self):
        """Força un nou naixement després de construir una segona sessió amb el comptador global reiniciat."""
        config = TrackerConfig(backend='botsort', confirmation_frames=1)
        first = TrackingSession(config, 30)
        first.update(box_frame())
        first.update(box_frame(1))
        second = TrackingSession(config, 30)
        second.update(box_frame(0, ()))
        for index in range(2, 6):
            first.update(box_frame(index, (0, 1, 2)))
            second.update(box_frame(index-1, ()))
        self.assertEqual(set(first.live), {1, 2, 3})
        self.assertEqual(second.live, {})

    @unittest.skipUnless(util.find_spec('boxmot'), 'Optional tracking-reid extra is not installed')
    def test_direct_session_rejects_variable_timing(self):
        """El límit temporal es respecta també quan una integració usa TrackingSession directament."""
        session = TrackingSession(TrackerConfig(backend='botsort'), 30)
        session.update(box_frame())
        frame = box_frame(1)
        frame = replace(frame, source=replace(frame.source, context=replace(frame.source.context, timestamp_s=.08)))
        with self.assertRaisesRegex(TrackingError, 'constant frame timing'):
            session.update(frame)
