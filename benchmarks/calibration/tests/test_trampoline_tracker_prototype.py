"""Verifica l'admissió feble i la semàntica de les absències del prototip."""

import unittest

from benchmarks.calibration.tools.trampoline_tracker_prototype import Candidate, Prototype


class TrampolinePrototypeTests(unittest.TestCase):
    """Comprova transicions amb candidats explícits i temps reals."""

    def make_tracker(self):
        """Prepara una variant que admet caixes molt febles després de confirmar."""
        return Prototype({'high_score': .1, 'max_lost_s': .5, 'confirmation_frames': 3},
                         {'motion': 'last', 'guard': True, 'weak_score': .001})

    def test_weak_measurement_keeps_id_after_confirmation_only(self):
        """La mateixa caixa feble només és una observació després del naixement fort."""
        tracker = self.make_tracker()
        weak = Candidate('weak',(100,100,140,200),.004)
        self.assertEqual(tracker.step(0,[weak])[0],{})
        for index in (1,2,3):
            strong = Candidate(f'strong-{index}',weak.box,.8)
            observed,_,_ = tracker.step(index/30,[strong])
        identity = observed['strong-3']
        observed,_,decisions = tracker.step(4/30,[weak])
        self.assertEqual(observed,{'weak':identity})
        self.assertEqual(decisions['very_weak_observed'],1)

    def test_missing_frame_produces_prediction_and_track_expires(self):
        """Un buit no exporta una observació i la retenció té límit temporal."""
        tracker = self.make_tracker()
        for index in range(3):
            candidate = Candidate(str(index),(100,100,140,200),.8)
            observed,_,_ = tracker.step(index/30,[candidate])
        self.assertEqual(tracker.step(.15,[])[:2],({},[observed['2']]))
        self.assertEqual(tracker.step(.62,[])[:2],({},[]))

    def test_mixed_box_can_leave_both_identities_unassigned(self):
        """Una caixa que engloba dos centres confirmats activa el rebuig mixt."""
        tracker = self.make_tracker()
        for index in range(3):
            left = Candidate('left',(80,100,120,185),.8)
            right = Candidate('right',(130,100,170,185),.8)
            observed,_,_ = tracker.step(index/30,[left,right])
        mixed = Candidate('mixed',(70,95,180,190),.9)
        assigned,predicted,decisions = tracker.step(.1,[mixed])
        self.assertEqual(assigned,{})
        self.assertCountEqual(predicted,observed.values())
        self.assertEqual(decisions['mixed_rejected'],1)

    def test_selective_guard_rejects_very_weak_return_after_longer_gap(self):
        """La mesura molt feble no reactiva un track si la darrera observació és antiga."""
        tracker = Prototype({'high_score': .1, 'max_lost_s': .5, 'confirmation_frames': 3},
                            {'motion': 'last', 'weak_score': .001, 'weak_guard': True})
        for index in range(3):
            strong = Candidate(str(index),(100,100,140,200),.8)
            observed,_,_ = tracker.step(index/30,[strong])
        weak = Candidate('weak',strong.box,.004)
        assigned,predicted,decisions = tracker.step(.30,[weak])
        self.assertEqual(assigned,{})
        self.assertEqual(predicted,[observed['2']])
        regular = Candidate('regular',strong.box,.04)
        assigned,_,_ = tracker.step(.34,[regular])
        self.assertEqual(assigned,{'regular':observed['2']})
