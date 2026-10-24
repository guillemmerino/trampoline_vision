"""Proves del registre temporal amb un port de backend controlat; no necessiten llibreries visuals."""

from unittest.mock import patch
import unittest

from helpers_tracking import tracking_frame
from trampoline_vision.tracking.backend import BackendUpdate
from trampoline_vision.tracking.config import TrackerConfig
from trampoline_vision.tracking.errors import TrackingError
from trampoline_vision.tracking.session import TrackingSession


class TrackingSessionTests(unittest.TestCase):
    """Comprova ordre temporal, transicions i rebuig de respostes incompatibles del backend."""

    def session(self):
        """Injecta només el port extern; la lògica de sessió i els contractes són els reals."""
        with patch("trampoline_vision.tracking.session.OCSortBackend") as factory:
            session = TrackingSession(TrackerConfig(), 25)
        return session, factory.return_value

    def test_lifecycle_observed_lost_recovered_finished(self):
        """Manté últim temps observat, distingeix predicció i emet cada transició una vegada."""
        session, backend = self.session()
        first = tracking_frame()
        box = first.candidates[0].measurement.bbox
        backend.update.return_value = BackendUpdate(((first.candidates[0].candidate_id, 0),), ((0, box),))
        observed = session.update(first)
        self.assertEqual(observed.tracks[0].track_id, "ocsort:0")
        self.assertEqual([e.kind for e in session.events], ["confirmed"])
        backend.update.return_value = BackendUpdate((), ((0, box),))
        lost = session.update(tracking_frame(1, .04, (), "missing"))
        self.assertEqual(lost.tracks[0].last_observed_timestamp_s, 0)
        self.assertEqual(lost.tracks[0].evidence, "predicted")
        self.assertEqual([e.kind for e in session.events], ["lost"])
        session.update(tracking_frame(2, .09, ()))
        self.assertEqual(session.events, ())
        recovered = tracking_frame(3, .15)
        backend.update.return_value = BackendUpdate(((recovered.candidates[0].candidate_id, 0),), ((0, box),))
        result = session.update(recovered)
        self.assertEqual([e.kind for e in session.events], ["recovered"])
        self.assertEqual(result.tracks[0].last_observed_timestamp_s, .15)
        backend.update.return_value = BackendUpdate((), ())
        result = session.update(tracking_frame(4, 1, ()))
        self.assertEqual(result.tracks[0].state, "finished")
        self.assertIsNone(result.tracks[0].bbox)
        self.assertEqual([e.kind for e in session.events], ["finished"])
        session.update(tracking_frame(5, 1.1, ()))
        self.assertEqual(session.events, ())

    def test_unconfirmed_and_reordered_detections(self):
        """-1 no crea identitat i les assignacions depenen del candidate_id encara que canviï l'ordre."""
        session, backend = self.session()
        frame = tracking_frame(people=("a", "b"))
        a, b = frame.candidates
        backend.update.return_value = BackendUpdate(((b.candidate_id, 0), (a.candidate_id, -1)), ((0, b.measurement.bbox),))
        result = session.update(frame)
        self.assertEqual(result.tracks[0].candidate_id, b.candidate_id)
        self.assertEqual(result.unassigned_candidate_ids, (a.candidate_id,))

    def test_sequence_validation_precedes_backend_mutation(self):
        """Rebutja salts d'índex, timestamps repetits i vídeos barrejats abans de tocar el backend."""
        session, backend = self.session()
        with self.assertRaises(TrackingError):
            session.update(tracking_frame(1, .1))
        backend.update.assert_not_called()
        backend.update.return_value = BackendUpdate((), ())
        session.update(tracking_frame(people=()))
        for frame in [tracking_frame(2, .1, ()), tracking_frame(1, 0, ()),
                      tracking_frame(1, .1, (), video_id="other")]:
            with self.subTest(frame=frame), self.assertRaises(TrackingError):
                session.update(frame)
        self.assertEqual(backend.update.call_count, 1)

    def test_backend_contract_failure_poison_session(self):
        """Una resposta incompleta no es converteix en èxit ni permet continuar un backend parcialment mutat."""
        session, backend = self.session()
        backend.update.return_value = BackendUpdate((), ())
        with self.assertRaisesRegex(TrackingError, "cover measured"):
            session.update(tracking_frame())
        with self.assertRaisesRegex(TrackingError, "failed previously"):
            session.update(tracking_frame())
        self.assertEqual(backend.update.call_count, 1)

    def test_expired_id_cannot_reappear(self):
        """Impedeix reutilitzar una identitat finalitzada dins d'una mateixa execució."""
        session, backend = self.session()
        first = tracking_frame()
        box = first.candidates[0].measurement.bbox
        backend.update.return_value = BackendUpdate(((first.candidates[0].candidate_id, 0),), ((0, box),))
        session.update(first)
        backend.update.return_value = BackendUpdate((), ())
        session.update(tracking_frame(1, 1, ()))
        frame = tracking_frame(2, 1.1)
        backend.update.return_value = BackendUpdate(((frame.candidates[0].candidate_id, 0),), ((0, box),))
        with self.assertRaisesRegex(TrackingError, "reused"):
            session.update(frame)

    def test_invalid_predictions_keep_identity_without_geometry(self):
        """La identitat pot mantenir-se sense caixa estimada, sense inventar coordenades o confiança."""
        session, backend = self.session()
        frame = tracking_frame()
        backend.update.return_value = BackendUpdate(((frame.candidates[0].candidate_id, 0),), ((0, None),))
        session.update(frame)
        backend.update.return_value = BackendUpdate((), ((0, None),))
        result = session.update(tracking_frame(1, .1, ()))
        self.assertEqual(result.tracks[0].track_id, "ocsort:0")
        self.assertIsNone(result.tracks[0].bbox)

    def test_tracker_configuration_is_strict_and_seconds_are_explicit(self):
        """Comprova arrodoniment temporal i rebuig d'algoritmes o valors no implementats."""
        self.assertEqual(TrackerConfig(max_lost_s=.51).lost_buffer, 16)
        self.assertEqual(TrackerConfig(max_lost_s=0).lost_buffer, 0)
        for value in [{"backend": "unselected"}, {"confidence_threshold": True}, {"confirmation_frames": 0},
                      {"max_lost_s": float("nan")}, {"unexpected": 1}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                TrackerConfig.from_dict(value)
