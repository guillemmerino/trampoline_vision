"""Solució global, abstenció i conservació d'evidències, sense models externs."""

from dataclasses import replace
import itertools
import math
import random
import tempfile
import unittest

from helpers_recovery import records_and_video,trace_from_records
from trampoline_vision.contracts.appearance import CandidateEmbedding,FrameAppearance
from trampoline_vision.recovery.association import associate
from trampoline_vision.recovery.config import AssociationParameters,RecoveryAuditConfig
from trampoline_vision.recovery.errors import RecoveryError
from trampoline_vision.recovery.features import FragmentFeatures,describe_fragments
from trampoline_vision.recovery.hungarian import linear_assignment
from trampoline_vision.recovery.pipeline import audit_recovery,prepare_recovery
from trampoline_vision.recovery.validation import build_validated_chains


def feature(fid,start,end,appearance=(1.,0.)):
    """Dues puntes coherents per a experiments d'assignació, no trajectòries esportives."""
    return FragmentFeatures(fid,start,end,(10.,10.),(10.,10.),(0.,0.),(0.,0.),20.,appearance)


class HungarianTests(unittest.TestCase):
    def test_optimum_against_exhaustive_search_and_ties(self):
        rng=random.Random(20261025)
        for n in range(1,5):
            for extra in (0,1,2):
                for _ in range(5):
                    matrix=[[rng.randrange(-2,5) for _ in range(n+extra)] for _ in range(n)]
                    selected=linear_assignment(matrix)
                    optimum=min(sum(matrix[i][j] for i,j in enumerate(cols)) for cols in itertools.permutations(range(n+extra),n))
                    self.assertEqual(sum(matrix[i][j] for i,j in enumerate(selected)),optimum)
                    self.assertEqual(len(set(selected)),n)
                    self.assertEqual(selected,linear_assignment(matrix))

    def test_global_conflict_is_not_greedy(self):
        matrix=[[1.,2.,10.,10.],[1.1,100.,10.,10.]]
        self.assertEqual(linear_assignment(matrix),(1,0))
        self.assertEqual(linear_assignment([]),())
        for value in ([[1],[2]],[[math.inf]],[[True]],[[]],[[1,2],[3]]):
            with self.assertRaises(ValueError):linear_assignment(value)


class RecoveryAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        records,video=records_and_video(self.tmp.name)
        self.trace=trace_from_records(records,video)
        self.geometry=RecoveryAuditConfig('test-geometry',strategy='geometry',parameters=AssociationParameters(
            appearance_weight=0,geometry_weight=.8,scale_weight=.1,time_weight=.1))

    def test_forward_links_abstention_and_appearance(self):
        fs=(feature('a',0,1),feature('b',1.2,2),feature('c',3,4,(-1.,0.)))
        proposals,selected,details=associate(fs,RecoveryAuditConfig('test'))
        self.assertEqual(selected,(('a','b'),))
        self.assertTrue(any(p.target_fragment_id=='c' and p.status=='rejected' for p in proposals))
        self.assertEqual(details['scope'],'single_full_video_matrix')
        self.assertIn('not_forward',details['gated_pairs'])

    def test_horizon_filters_edges_not_whole_video_windows(self):
        fs=(feature('a',1.8,1.9),feature('b',2.1,2.2),feature('c',8,9))
        _,selected,_=associate(fs,self.geometry)
        self.assertIn(('a','b'),selected)
        self.assertFalse(any(b=='c' for a,b in selected))

    def test_trace_preserved_and_disabled_does_not_invent_actors(self):
        before=repr(self.trace)
        prepared,_,chains,details=audit_recovery(self.trace,self.geometry)
        self.assertIs(prepared.trace,self.trace)
        self.assertEqual(repr(self.trace),before)
        self.assertEqual(sum(len(c) for c in chains),len(prepared.fragments))
        disabled=replace(self.geometry,strategy='disabled')
        _,proposals,chains,details=audit_recovery(self.trace,disabled)
        self.assertEqual((proposals,chains),((),()))
        self.assertFalse(details['association_executed'])
        self.assertFalse(details['review']['automatic_fragment_splitting'])

    def test_invalid_chain_rejected(self):
        fs=prepare_recovery(self.trace).fragments
        a,b=fs[0].fragment_id,fs[1].fragment_id
        for links in (((a,a),),((a,'missing'),),((a,b),(a,b))):
            with self.assertRaises(RecoveryError):build_validated_chains(fs,links)

    def test_appearance_coverage_fingerprint_and_dimensions(self):
        prepared=prepare_recovery(self.trace)
        appearances=[FrameAppearance(f.context,'model-a',tuple(CandidateEmbedding(c.candidate.candidate_id,(1.,0.))
            for c in f.candidates if c.candidate.measurement)) for f in self.trace.frames]
        fs=describe_fragments(prepared,appearances)
        self.assertTrue(all(f.appearance==(1.,0.) for f in fs))
        invalid=[appearances[:-1],appearances+[appearances[-1]],
                 [replace(appearances[0],model_fingerprint='other'),*appearances[1:]]]
        if appearances[0].embeddings:
            invalid.append([replace(appearances[0],embeddings=()),*appearances[1:]])
        for values in invalid:
            with self.assertRaises(RecoveryError):describe_fragments(prepared,values)
        with self.assertRaises(RecoveryError):audit_recovery(self.trace,RecoveryAuditConfig('appearance'))

    def test_strict_profile_rejects_apply_drafts_and_unknown_fields(self):
        from dataclasses import asdict
        raw={'schema_version':'1.0','task':'audit_tracking_recovery',**asdict(self.geometry)}
        self.assertEqual(RecoveryAuditConfig.from_dict(raw),self.geometry)
        for changes in ({'mode':'apply'},{'status':'validated'},{'schema_version':'0.1-draft'},{'enabled':True},
                        {'revision':True},{'parameters':{'unexpected':1}}):
            with self.assertRaises(ValueError):RecoveryAuditConfig.from_dict({**raw,**changes})
        for changes in ({'max_gap_s':float('nan')},{'no_link_cost':True},{'appearance_weight':.2},{'max_scale_ratio':1}):
            with self.assertRaises(ValueError):AssociationParameters(**changes)
