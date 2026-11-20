"""Proves aparellades amb vídeo sintètic real, sense models ni seguiment temporal."""

import argparse
from contextlib import redirect_stdout
import gzip
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from benchmarks.calibration.engine.common import digest, sha256
from benchmarks.calibration.tools.compare_zones import VARIANTS, previous_zone, run


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'Cal FFmpeg per generar el clip sintètic')
class ZoneComparisonTests(unittest.TestCase):
    """Contrasta guanys per flexibilitzar la zona i conserva totes les fonts i referències."""

    def setUp(self):
        """Crea dos instants amb gimnasta exterior a la zona antiga i una altra persona interior."""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        video = self.root/'video.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=black:s=160x120:r=2',
                        '-frames:v','2','-c:v','libx264','-pix_fmt','yuv420p',str(video)],check=True)
        checksum = sha256(video)
        corpus = {'cases':[{'case_id':'case','path':'video.mp4','sha256':checksum,
                  'video':{'width_px':160,'height_px':120,'fps':2.,'frame_count':2}}]}
        samples = [{'key':f'case:{i}','case_id':'case','frame_index':i,'timestamp_s':i/2,
            'width':160,'height':120,'partition':'development','video_sha256':checksum,
            'reference':{'state':'visible','bbox_xyxy':[15,40,40,100]},
            'variants':{'detector':{'boxes':[{'det_id':0,'bbox_xyxy':[15,40,40,100],'confidence':.6},
                                           {'det_id':1,'bbox_xyxy':[105,40,130,100],'confidence':.8}]}}} for i in range(2)]
        self.bundle = {'schema_version':'1.0','run_signature':'synthetic',
            'detectors':{'detector':{'model':'yolov8m','confidence':.001,'nms_iou':.7}},'frames':samples}
        config = {'schema_version':'1.0','box_preparation':{'enabled':True},
                  'representative_boxes':{'zone':[.06,.25,.94,.93],'zone_mode':'soft','max_candidates':12}}
        plan = {'schema_version':'1.0','variants':list(VARIANTS),'detector':'detector',
                'expected_samples_per_case':2,'cases':[{'id':'case','panel':'right'}]}
        for name,value in [('corpus',corpus),('bundle',self.bundle),('config',config),('plan',plan)]:
            (self.root/f'{name}.json').write_text(json.dumps(value))
        self.args = argparse.Namespace(dataset=self.root,bundle=self.root/'bundle.json',decisions=None,
            config=self.root/'config.json',plan=self.root/'plan.json',output=self.root/'output',
            allow_provisional_references=True,dry_run=False,case=None)

    def execute(self):
        """Captura el progrés perquè la prova només informi el seu resultat."""
        with redirect_stdout(io.StringIO()):
            return run(self.args)

    def test_real_video_audit_and_paired_metrics_with_human_box(self):
        """Flexibilitzar recupera la caixa exterior sense alterar-la ni confondre-la amb la referència d’IA."""
        state = {'schema_version':'1.0','run_signature':'synthetic','bundle_sha256':digest(self.bundle),
            'revision':1,'reviewer':'test','updated_at':None,'entries':{'case:0':{
                'presence':'visible','reference':{'verdict':'missing','bbox_xyxy':None,'source':'none','candidate':None},
                'detectors':{'detector':{'verdict':'partial','candidate_id':0}},'notes':'','updated_at':''}}}
        self.args.decisions = self.root/'decisions.json'
        self.args.decisions.write_text(json.dumps(state))
        summary = self.execute()
        self.assertEqual(summary['scope']['annotated_frames'],2)
        self.assertEqual(summary['totals']['all']['previous_hard']['ai_reference:covered_at_090'],0)
        self.assertEqual(summary['totals']['all']['centered_soft']['ai_reference:covered_at_090'],2)
        self.assertEqual(summary['totals']['all']['centered_soft']['human_useful_detection:covered_at_095'],1)
        self.assertEqual(summary['paired_changes']['ai_reference:previous_hard_to_centered_soft:covered_at_090:gained'],2)
        with gzip.open(self.args.output/'frames.jsonl.gz','rt') as stream:
            rows = [json.loads(line) for line in stream]
        self.assertEqual(len(rows[0]['source']['detections']),2)
        self.assertEqual(len(rows[0]['variants']['previous_hard']['selection_audit']['selections']),2)
        self.assertIn('pending_human_validation', rows[0]['reference_status'])
        self.assertTrue((self.args.output/'case/index.html').is_file())
        self.assertTrue((self.args.output/'completed.json').is_file())
        self.assertEqual(len((self.args.output/'discrepancies.jsonl').read_text().splitlines()),2)
        with self.assertRaisesRegex(ValueError,'new output'):
            self.execute()

    def test_preflight_and_invalid_inputs_do_not_create_output(self):
        """El preflight no calcula resultats ni accepta silenciosament referències IA o vídeos diferents."""
        self.args.dry_run = True
        self.assertEqual(self.execute()['videos'],1)
        self.assertFalse(self.args.output.exists())
        self.args.allow_provisional_references = False
        with self.assertRaisesRegex(ValueError,'provisional'):
            self.execute()
        self.args.allow_provisional_references = True
        (self.root/'video.mp4').write_bytes(b'corrupted')
        with self.assertRaisesRegex(ValueError,'SHA-256'):
            self.execute()
        self.assertFalse(self.args.output.exists())

    def test_evaluation_reference_does_not_influence_selected_boxes(self):
        """Canviar la referència modifica el diagnòstic però manté exactament totes les seleccions."""
        self.execute()
        with gzip.open(self.args.output/'frames.jsonl.gz','rt') as stream:
            before = json.loads(next(stream))
        self.bundle['frames'][0]['reference']['bbox_xyxy'] = [60, 10, 80, 30]
        self.args.bundle.write_text(json.dumps(self.bundle))
        self.args.output = self.root/'second'
        self.execute()
        with gzip.open(self.args.output/'frames.jsonl.gz','rt') as stream:
            after = json.loads(next(stream))
        for name in VARIANTS:
            self.assertEqual(before['variants'][name]['candidates'],after['variants'][name]['candidates'])
        self.assertNotEqual(before['variants']['centered_soft']['metrics'],after['variants']['centered_soft']['metrics'])

    def test_historical_zones_are_not_both_assumed_to_be_right(self):
        """La comparació conserva la geometria anterior de cada costat."""
        self.assertAlmostEqual(previous_zone('left')[0], .0414)
        self.assertAlmostEqual(previous_zone('left')[2], .6486)
        self.assertAlmostEqual(previous_zone('right')[0], .342)
        self.assertAlmostEqual(previous_zone('right')[2], .958)
