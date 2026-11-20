"""Casos controlats de preparació de caixes: cobertura, ambigüitat i traçabilitat.

No executen YOLO ni tracking. Comproven errors que podrien perdre el gimnasta
o confondre la contenció geomètrica amb una identitat de persona.
"""

from dataclasses import asdict, replace
from itertools import permutations
import json
import unittest

from trampoline_vision.contracts.geometry import BoundingBox
from trampoline_vision.contracts.observations import DetectionProvenance, FrameContext, FrameDetections, PersonBoxDetection
from trampoline_vision.contracts.tracking import BoxRelation, TrackingFrame
from trampoline_vision.preparation.boxes import group_boxes, prepare_boxes, select_representative
from trampoline_vision.preparation.config import BoxPreparationPolicy, PreparationConfig
from trampoline_vision.preparation.pipeline import prepare_frame, prepare_frames
from trampoline_vision.results.preparation import preparation_record


def detection(identifier, coordinates, score=.8, index=0):
    """Crea una detecció observada amb referència pròpia a una fila CSV sintètica."""
    return PersonBoxDetection(identifier, BoundingBox(*coordinates), score,
                              DetectionProvenance('synthetic.csv', f'csv_line:{index+2}', 0, index, 'test', 'original'))


def frame(*detections, status='present'):
    """Agrupa deteccions en un fotograma original, sense construir un vídeo fictici."""
    return FrameDetections(FrameContext('case', 0, 0., .04, 960, 1080), tuple(detections), status)


class BoxPreparationTests(unittest.TestCase):
    """Protegeix la recuperació de cada font i el caràcter no temporal de les decisions."""

    def setUp(self):
        """Activa expressament la política experimental; el default del projecte continua pass-through."""
        self.policy = BoxPreparationPolicy(enabled=True)
        self.config = PreparationConfig(box_preparation=self.policy)

    def test_default_preserves_order_ids_measurements_and_no_relations(self):
        """Una configuració antiga manté una detecció per candidat i el format d'ID existent."""
        source = frame(detection('b', (0,0,100,200), .01, 2), detection('a', (1,0,101,200), .8, 0))
        result = prepare_frame(source)
        self.assertEqual([c.candidate_id for c in result.candidates], ['0:box_candidate:2', '0:box_candidate:0'])
        self.assertEqual([c.measurement.score for c in result.candidates], [.01,.8])
        self.assertEqual([c.issues for c in result.candidates], [('pose_not_available',)]*2)
        self.assertEqual(result.relations, ())

    def test_larger_observed_representative_preserves_every_original_byte_value(self):
        """El representant pot tenir menys confiança: més cobertura sense score inventat ni caixa fusionada."""
        a=detection('a',(10,10,110,210),.8,0);b=detection('b',(8,8,112,212),.05,1)
        source=frame(a,b);before=asdict(source);result=prepare_frame(source,self.config)
        self.assertIs(result.source,source)
        self.assertEqual(len(result.candidates),1)
        c=result.candidates[0]
        self.assertEqual(c.source_detection_ids,('b','a'))
        self.assertIs(c.measurement.bbox,b.bbox)
        self.assertEqual(c.measurement.score,.05)
        self.assertEqual(c.measurement.source,'detector')
        self.assertIn('box_duplicates_grouped',c.issues)
        self.assertEqual(asdict(source),before)
        exported=json.loads(json.dumps(preparation_record(result,self.config)))
        self.assertEqual(exported['source'],json.loads(json.dumps(before)))
        self.assertEqual(exported['effective_config']['box_preparation']['enabled'],True)
        self.assertEqual(len(exported['source']['detections']),2)

    def test_grouping_is_deterministic_under_input_permutations(self):
        """Ordre i desempats no depenen de l'ordre extern ni d'adreces d'objectes."""
        boxes=(detection('a',(0,0,100,200),.8,0), detection('b',(2,0,102,200),.01,1), detection('c',(300,0,400,200),.8,2))
        results=[prepare_boxes(frame(*order),self.policy) for order in permutations(boxes)]
        self.assertTrue(all((r.candidates,r.relations)==(results[0].candidates,results[0].relations) for r in results))

    def test_chain_does_not_absorb_incompatible_endpoints(self):
        """B és proper a A i C, però A i C no es poden fusionar a través de B."""
        source=frame(detection('a',(0,0,100,200),.8,0), detection('b',(14,0,114,200),.01,1), detection('c',(28,0,128,200),.001,2))
        # Relaxar només la salvaguarda de cobertura per aïllar la unió en cadena.
        result=prepare_boxes(source,replace(self.policy,min_representative_coverage=.8))
        self.assertEqual({frozenset(c.source_detection_ids) for c in result.candidates},{frozenset(('a','b')),frozenset(('c',))})

    def test_larger_area_cannot_trim_a_member_foot_extent(self):
        """Regressió del frame real 435: una caixa més ampla però curta retallava la bona."""
        source=frame(detection('approved',(296.3187,646.6528,355.3256,823.5241),.01414,72),
                     detection('wider',(297.0644,646.8972,369.5883,792.6632),.00227,105))
        result=prepare_boxes(source,self.policy)
        self.assertEqual(len(result.candidates),2)
        self.assertEqual({c.source_detection_ids for c in result.candidates},{('approved',),('wider',)})

    def test_coverage_groups_nested_boxes_that_survive_original_nms(self):
        """IoU 0,694 sobreviu a NMS 0,7; una caixa observada més gran cobreix les dues fonts."""
        source=frame(detection('whole',(0,0,120,240),.8,0),detection('nested',(10,20,110,220),.01,1))
        result=prepare_boxes(source,self.policy)
        self.assertEqual(len(result.candidates),1)
        self.assertEqual(result.candidates[0].source_detection_ids,('whole','nested'))
        self.assertEqual(result.candidates[0].measurement.bbox,source.detections[0].bbox)

    def test_half_body_and_foreground_helper_are_relations_not_merges(self):
        """Ni el mig cos ni un gimnasta feble dins l'assistent desapareixen de les hipòtesis."""
        for coordinates in [(0,0,100,100),(15,20,85,150)]:
            with self.subTest(coordinates=coordinates):
                source=frame(detection('large',(0,0,100,300),.9,0),detection('small',coordinates,.001,1))
                result=prepare_boxes(source,self.policy)
                self.assertEqual(len(result.candidates),2)
                self.assertEqual(len(result.relations),1)
                relation=result.relations[0]
                self.assertEqual(relation.kind,'ambiguous_containment')
                self.assertEqual(relation.ios,1)
                small=next(c for c in result.candidates if c.candidate_id==relation.smaller_candidate_id)
                self.assertIn('possible_partial',small.issues)
                self.assertEqual(small.measurement.score,.001)

    def test_multiple_possible_containers_do_not_duplicate_source_membership(self):
        """Una caixa pot estar relacionada amb dos contenidors sense pertànyer a dos grups."""
        source=frame(detection('a',(0,0,100,200),.8,0),detection('b',(5,0,105,200),.8,1),detection('s',(25,25,75,100),.05,2))
        result=prepare_boxes(source,self.policy)
        self.assertEqual(len(result.candidates),3)
        self.assertEqual(len(result.relations),2)
        self.assertEqual(sorted(ref for c in result.candidates for ref in c.source_detection_ids),['a','b','s'])

    def test_neighbours_and_horizontal_gymnasts_are_not_verticality_filtered(self):
        """No imposa formes humanes dretes ni elimina caixes febles o disjuntes."""
        source=frame(detection('horizontal',(0,0,200,50),.001,0),detection('near',(210,0,410,50),0,1))
        result=prepare_boxes(source,self.policy)
        self.assertEqual(len(result.candidates),2)
        self.assertEqual(result.relations,())

    def test_empty_missing_and_lazy_stream_preserve_context(self):
        """El preparador no salta fotogrames buits ni anticipa el consum del stream."""
        visited=[]
        def sources():
            """Registra l'accés per detectar consum anticipat accidental."""
            for i in range(2):
                visited.append(i)
                yield replace(frame(status='missing' if i else 'present'),context=FrameContext('case',i,i*.04,.04,960,1080))
        stream=prepare_frames(sources(),self.config)
        self.assertFalse(visited)
        first=next(stream);self.assertEqual(visited,[0])
        second=next(stream)
        self.assertEqual(first.candidates,());self.assertEqual(second.source.source_status,'missing')
        self.assertEqual(prepare_boxes(frame(),self.policy).relations,())

    def test_repeated_external_indices_use_unique_detection_ids(self):
        """La procedència d'una font personalitzada no substitueix la unicitat de detection_id."""
        result=prepare_boxes(frame(detection('a',(0,0,100,100)),detection('b',(200,0,300,100))),self.policy)
        self.assertEqual(len({c.candidate_id for c in result.candidates}),2)

    def test_rejects_invalid_sources_and_configurations(self):
        """Rebutja errors de tipus i llindars abans de crear una interpretació preparada."""
        for changes in [{'enabled':1},{'min_size_similarity':True},{'min_containment_ios':float('nan')},
                        {'min_contained_area_ratio':.8,'max_contained_area_ratio':.2}]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):replace(self.policy,**changes)
        for raw in [{'box_preparation':None},{'box_preparation':{'typo':True}}]:
            with self.assertRaises(ValueError):PreparationConfig.from_dict({'schema_version':'1.0',**raw})
        self.assertEqual(PreparationConfig.from_dict({'schema_version':'1.0','box_preparation':asdict(self.policy)}),self.config)
        with self.assertRaises(ValueError):select_representative(())
        with self.assertRaises(ValueError):group_boxes([],self.policy)

    def test_relation_contract_checks_references_duplicates_and_metrics(self):
        """Una relació ha de ser local, inequívoca i tenir mètriques finites vàlides."""
        prepared=prepare_boxes(frame(detection('a',(0,0,100,200),.8,0),detection('s',(25,25,75,100),.01,1)),self.policy)
        relation=prepared.relations[0]
        for changes in [{'ios':float('inf')},{'iou':True},{'area_ratio':0},{'kind':'same_person'},
                        {'larger_candidate_id':relation.smaller_candidate_id}]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):replace(relation,**changes)
        with self.assertRaises(ValueError):replace(prepared,relations=(relation,relation))
        with self.assertRaises(ValueError):replace(prepared,relations=(replace(relation,larger_candidate_id='unknown'),))
        with self.assertRaises(ValueError):TrackingFrame(prepared.source,prepared.candidates,[relation])
