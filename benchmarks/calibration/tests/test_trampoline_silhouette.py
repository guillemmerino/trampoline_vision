"""Controls del manteniment d'identitat amb confiança i silueta separades."""

from pathlib import Path
from types import SimpleNamespace
import unittest

import numpy as np

from benchmarks.calibration.engine.common import read_json
from benchmarks.calibration.tools.trampoline_silhouette import SilhouettePrototype
from benchmarks.calibration.tools.trampoline_tracker_prototype import Candidate

PLAN = Path(__file__).resolve().parents[1]/'config/studies/trampoline-silhouette-v1.json'


class SilhouetteMaintenanceTests(unittest.TestCase):
    """Comprova que millorar el cost d'una caixa no canvia el seu score ni el naixement."""

    def setUp(self):
        """Carrega els valors exactes del pla de simulació."""
        self.plan = read_json(PLAN)
        self.tracker = SilhouettePrototype(self.plan,self.plan['variants']['last_silhouette'])

    def test_low_score_is_considered_only_after_confirmation(self):
        """Una caixa feble amb silueta pot mantenir un ID confirmat amb la mateixa confiança."""
        weak = Candidate('weak',(80,100,120,185),.004,silhouette=.60)
        self.assertEqual(self.tracker.step(0,[weak])[0],{})
        for index in (1,2,3):
            strong = Candidate(f'strong-{index}',weak.box,.80)
            observed,_,_ = self.tracker.step(index/30,[strong])
        identity = observed['strong-3']
        assigned,_,decisions = self.tracker.step(4/30,[weak])
        self.assertEqual(assigned,{'weak':identity})
        self.assertEqual(weak.score,.004)
        self.assertEqual(decisions['maintenance_considered'],1)

    def test_foreground_cannot_resolve_two_competing_actors_alone(self):
        """El suport de la caixa beneficia igual els dos actors i es manté el buit."""
        weak = Candidate('weak',(80,100,120,185),.004,silhouette=.85)
        cost = np.array([[.40],[.43]])
        tracks = [SimpleNamespace(timestamp=.1),SimpleNamespace(timestamp=.1)]
        result = self.tracker.adjust_maintenance(cost,[False],tracks,[weak],.13,[],.86)
        self.assertTrue(np.all(cost>=.86))
        self.assertEqual(result['maintenance_ambiguous'],1)

    def test_silhouette_never_reopens_spatially_impossible_link(self):
        """Un senyal de primer pla fort no reobre una associació fora de la cerca."""
        weak = Candidate('weak',(80,100,120,185),.004,silhouette=1.)
        cost = np.array([[1e5]])
        self.tracker.adjust_maintenance(cost,[False],[SimpleNamespace(timestamp=.1)],[weak],.13,[],.86)
        self.assertGreater(cost[0,0],.86)
