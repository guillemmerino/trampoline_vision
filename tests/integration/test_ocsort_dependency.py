"""Verificació de l'API externa escollida, independent del futur adaptador.

Només s'executa si s'ha instal·lat l'extra tracking. Les caixes són sintètiques;
no es prepara OpenPose ni es mesura precisió esportiva. Un canvi incompatible
de dependència ha de fallar aquí abans d'afectar un vídeo real.
"""

from importlib import metadata, util
import unittest


@unittest.skipUnless(util.find_spec("trackers"), "Optional tracking extra is not installed")
class OCSortDependencyTests(unittest.TestCase):
    """Comprova IDs, referències d'entrada i predicció pública sense llegir atributs privats."""

    def test_external_detections_timestamps_and_missing_frame(self):
        """Confirma l'API fixada, l'ID zero, el buidatge temporal i la recuperació curta."""
        import numpy as np
        import supervision as sv
        from trackers import OCSORTTracker

        self.assertEqual(metadata.version("trackers"), "2.6.1")
        tracker = OCSORTTracker(minimum_consecutive_frames=1, high_conf_det_threshold=0.5)
        identities = None
        for timestamp in (0.0, 0.04, 0.09):
            detections = sv.Detections(
                xyxy=np.array([[10, 10, 30, 50], [70, 10, 90, 50]], dtype=np.float32),
                confidence=np.array([0.9, 0.8], dtype=np.float32),
                data={"candidate_id": np.array(["a", "b"])},
            )
            result = tracker.update(detections, timestamp=timestamp)
            mapping = dict(zip(result.data["candidate_id"], result.tracker_id.tolist()))
            if timestamp > 0:
                self.assertTrue(all(value >= 0 for value in mapping.values()))
                self.assertEqual(len(set(mapping.values())), 2)
                if identities is not None:
                    self.assertEqual(mapping, identities)
                identities = mapping
        self.assertIn(0, identities.values())

        # update retorna deteccions actuals; tracked_objects exposa estimacions sense confiança observada.
        empty = tracker.update(sv.Detections.empty(), timestamp=0.13)
        self.assertEqual(len(empty), 0)
        predictions = tracker.tracked_objects
        self.assertEqual(set(predictions.tracker_id.tolist()), set(identities.values()))
        self.assertIsNone(predictions.confidence)
        recovered = tracker.update(detections, timestamp=0.18)
        self.assertEqual(dict(zip(recovered.data["candidate_id"], recovered.tracker_id.tolist())), identities)

        # OC-SORT no associa aquesta detecció feble, però la retorna amb la referència intacta.
        weak = sv.Detections(xyxy=np.array([[10, 10, 30, 50]], dtype=np.float32),
                             confidence=np.array([0.1], dtype=np.float32),
                             data={"candidate_id": np.array(["weak"])})
        result = tracker.update(weak, timestamp=0.22)
        self.assertEqual(result.tracker_id.tolist(), [-1])
        self.assertEqual(result.data["candidate_id"].tolist(), ["weak"])

        # Amb un buit llarg s'esgoten les hipòtesis vives; reset separa execucions i vídeos.
        tracker.update(sv.Detections.empty(), timestamp=3.0)
        self.assertEqual(len(tracker.tracked_objects), 0)
        tracker.reset()
        self.assertEqual(len(tracker.tracked_objects), 0)
