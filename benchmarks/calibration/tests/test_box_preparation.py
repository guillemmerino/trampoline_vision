"""Recorregut independent de preparació: bundle sintètic, exportació i cobertura.

Protegeix la separació entre referències d'avaluació i decisions de l'algoritme,
i la possibilitat de revisar totes les fonts des del JSONL publicat.
"""

from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest

from benchmarks.calibration.__main__ import main
from benchmarks.calibration.engine.common import verify_artifacts
from benchmarks.calibration.tools.prepare_boxes import coverage_metrics, run
from trampoline_vision.contracts.geometry import BoundingBox
from trampoline_vision.preparation.config import BoxPreparationPolicy


class BoxPreparationCommandTests(unittest.TestCase):
    """Comprova publicació sense sobreescriptura i conservació de caixes agrupades."""

    def setUp(self):
        """Genera dos frames artificials amb una parella duplicada i una contenció parcial."""
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        self.config=self.root/'config.json';self.corpus=self.root/'corpus.json';self.bundle=self.root/'bundle.json'
        self.config.write_text(json.dumps({'schema_version':'1.0','box_preparation':asdict(BoxPreparationPolicy(enabled=True))}))
        self.corpus.write_text(json.dumps({'cases':[{'case_id':'case','video':{'fps':25,'width_px':960,'height_px':1080,'frame_count':2}}]}))
        frames=[]
        for i in range(2):
            boxes=[{'det_id':0,'bbox_xyxy':[10,10,110,210],'confidence':.8},
                   {'det_id':1,'bbox_xyxy':[8,8,112,212],'confidence':.05},
                   {'det_id':2,'bbox_xyxy':[25,25,75,100],'confidence':.01}]
            frames.append({'key':f'case:{i}','case_id':'case','frame_index':i,'timestamp_s':i/25,
                           'width':960,'height':1080,'partition':'development','video_sha256':'video','reference_sha256':'reference',
                           'reference':{'state':'visible','bbox_xyxy':[10,10,110,210]},'variants':{'detector':{'boxes':boxes}}})
        self.bundle.write_text(json.dumps({'schema_version':'1.0','run_signature':'test','detectors':{'detector':{'confidence':.001}},'frames':frames}))

    def test_exports_full_sources_config_relations_and_verified_artifacts(self):
        """Agrupar dues deteccions preserva les tres fonts i desa les relacions separadament."""
        out=self.root/'output'
        result=run(self.bundle,self.config,out,corpus_path=self.corpus,detector='detector')
        self.assertEqual(result['counts']['source_boxes'],6)
        self.assertEqual(result['counts']['candidates'],4)
        self.assertEqual(result['counts']['grouped_alternatives'],2)
        self.assertEqual(result['counts']['relations'],2)
        self.assertEqual(result['counts']['lost_covered_at_090'],0)
        rows=[json.loads(line) for line in (out/'frames.jsonl').read_text().splitlines()]
        self.assertEqual(len(rows[0]['source']['detections']),3)
        self.assertEqual(rows[0]['candidates'][0]['source_detection_ids'],['0:box:1','0:box:0'])
        self.assertEqual(rows[0]['source']['detections'][0]['bbox']['x_min'],10)
        self.assertEqual(rows[0]['source']['detections'][1]['score'],.05)
        verify_artifacts(out,json.loads((out/'checksums.json').read_text()))
        with self.assertRaisesRegex(ValueError,'new preparation output'):
            run(self.bundle,self.config,out,corpus_path=self.corpus,detector='detector')

    def test_reference_changes_do_not_change_prepared_candidates(self):
        """Les referències són exclusivament diagnòstiques, mai una pista d'agrupament."""
        first=self.root/'first';second=self.root/'second'
        run(self.bundle,self.config,first,corpus_path=self.corpus,detector='detector')
        data=json.loads(self.bundle.read_text())
        for f in data['frames']:f['reference']['bbox_xyxy']=[500,500,600,700]
        self.bundle.write_text(json.dumps(data))
        run(self.bundle,self.config,second,corpus_path=self.corpus,detector='detector')
        a=json.loads((first/'frames.jsonl').read_text().splitlines()[0]);b=json.loads((second/'frames.jsonl').read_text().splitlines()[0])
        self.assertEqual(a['candidates'],b['candidates']);self.assertEqual(a['relations'],b['relations'])

    def test_coverage_accepts_margin_and_exposes_area_cost(self):
        """Una caixa més gran pot cobrir el gimnasta encara que l'IoU sigui baix."""
        result=coverage_metrics([BoundingBox(0,0,200,400)],[10,10,110,210])
        self.assertTrue(result['covered_at_090']);self.assertTrue(result['covered_at_090_area4'])
        self.assertEqual(result['min_area_ratio_at_090'],4)
        huge=coverage_metrics([BoundingBox(0,0,960,1080)],[10,10,110,210])
        self.assertTrue(huge['covered_at_090']);self.assertFalse(huge['covered_at_090_area4'])

    def test_public_command_dispatches_explicit_preparation(self):
        """La mateixa comanda del banc exposa el preparador, sense inferència ni tracking."""
        from contextlib import redirect_stdout
        import io
        with redirect_stdout(io.StringIO()):
            code=main(['prepare-boxes','--bundle',str(self.bundle),'--config',str(self.config),
                       '--corpus',str(self.corpus),'--detector','detector','--output',str(self.root/'cli')])
        self.assertEqual(code,0)
