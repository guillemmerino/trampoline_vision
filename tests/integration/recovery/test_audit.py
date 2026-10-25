"""CLI i publicació d'auditoria amb cache real SQLite i sondeig controlat."""

from contextlib import redirect_stdout,redirect_stderr
from dataclasses import asdict
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from helpers_recovery import write_tracking_export,trace_from_records
from trampoline_vision.application.recovery_audit import audit_tracking_recovery
from trampoline_vision.contracts.appearance import CandidateEmbedding,FrameAppearance
from trampoline_vision.infrastructure.artifacts import publish_exclusive
from trampoline_vision.infrastructure.embedding_cache import EmbeddingCache,ReadOnlyEmbeddingCache
from trampoline_vision.ingestion.recovery import sha256_file
from trampoline_vision.interfaces.cli.main import main
from trampoline_vision.recovery.config import AssociationParameters,RecoveryAuditConfig
from trampoline_vision.recovery.errors import RecoveryError


class RecoveryAuditIntegrationTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.report,self.tracks,self.video,self.records=write_tracking_export(self.root)
        self.video.path.write_bytes(b'synthetic-video-source-for-mocked-probe')
        self.trace=trace_from_records(self.records,self.video)
        self.config=self.root/'profile.json'
        self.set_config('geometry')
        self.probe=patch('trampoline_vision.application.recovery_audit.probe_video',return_value=self.video)
        self.probe.start()
        self.addCleanup(self.probe.stop)

    def set_config(self,strategy):
        p=AssociationParameters(appearance_weight=0,geometry_weight=.8,scale_weight=.1,time_weight=.1) if strategy=='geometry' else AssociationParameters()
        config=RecoveryAuditConfig('test-profile',strategy=strategy,parameters=p)
        self.config.write_text(json.dumps({'schema_version':'1.0','task':'audit_tracking_recovery',**asdict(config)}))

    def run_cli(self,output,*args):
        err=io.StringIO()
        with redirect_stdout(io.StringIO()),redirect_stderr(err):
            code=main(['audit-recovery','--tracking-report',str(self.report),'--config',str(self.config),'--output',str(output),*args])
        return code,err.getvalue()

    def make_cache(self):
        identity={'provider':'synthetic-test','weights_sha256':'a'*64,'preprocessing':'synthetic-unit-vectors',
                  'dimensions':2,'device':'cpu','threads':1,'versions':{}}
        fingerprint=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
        detections=self.root/'detections.csv'
        detections.write_text('synthetic-source-for-cache-identity')
        cache_identity={'video_id':self.video.video_id,'video_sha256':sha256_file(self.video.path),
            'detections_sha256':sha256_file(detections),'source_format':'person_boxes_csv',
            'timeline_sha256':hashlib.sha256(json.dumps([self.video.timestamps_s,self.video.frame_durations_s]).encode()).hexdigest(),
            'model_fingerprint':fingerprint}
        cache=EmbeddingCache(self.root/'cache',cache_identity,fingerprint)
        for frame in self.trace.frames:
            prepared=SimpleNamespace(source=SimpleNamespace(context=frame.context,source_status=frame.source_status),
                candidates=tuple(c.candidate for c in frame.candidates))
            appearance=FrameAppearance(frame.context,fingerprint,tuple(CandidateEmbedding(c.candidate_id,(1.,0.)) for c in prepared.candidates if c.measurement))
            cache.put(prepared,appearance)
        path=cache.path
        cache.close()
        report=json.loads(self.report.read_text())
        report['appearance']={**identity,'fingerprint':fingerprint}
        report['inputs']['detections']={'path':str(detections),'sha256':sha256_file(detections)}
        self.report.write_text(json.dumps(report))
        return path,detections

    def test_geometry_cli_snapshots_and_preserves_originals(self):
        originals={p:p.read_bytes() for p in (self.report,self.tracks,self.video.path,self.config)}
        output=self.root/'audit.json'
        code,error=self.run_cli(output)
        self.assertEqual(code,0,error)
        result=json.loads(output.read_text())
        self.assertFalse(result['applied'])
        self.assertEqual(result['status'],'experimental')
        self.assertEqual(result['profile']['snapshot'],json.loads(self.config.read_text()))
        self.assertEqual(result['profile']['sha256'],sha256_file(self.config))
        self.assertTrue(result['code']['source_tree_sha256'])
        self.assertEqual(result['validation']['identity_accuracy'],'not_evaluated')
        self.assertEqual(result['totals']['observed_samples'],sum(t['evidence']=='observed' for r in self.records for t in r['tracks']))
        self.assertTrue((self.root/'audit.links.jsonl').exists())
        for p,content in originals.items():self.assertEqual(p.read_bytes(),content)
        self.assertEqual(self.run_cli(output)[0],2)

    def test_native_cache_is_reused_read_only_without_inference(self):
        path,detections=self.make_cache()
        self.set_config('geometry_appearance')
        before=path.read_bytes()
        code,error=self.run_cli(self.root/'appearance.json','--appearance-cache',str(path))
        self.assertEqual(code,0,error)
        self.assertEqual(path.read_bytes(),before)
        self.assertFalse(Path(str(path)+'-wal').exists())
        result=json.loads((self.root/'appearance.json').read_text())
        self.assertIn('appearance_inference',result['capabilities_not_executed'])
        self.assertEqual(result['inputs']['detections']['sha256'],sha256_file(detections))

    def test_cache_missing_or_wrong_identity_or_partial_publishes_nothing(self):
        path,detections=self.make_cache()
        self.set_config('geometry_appearance')
        output=self.root/'missing.json'
        self.assertEqual(self.run_cli(output)[0],2)
        self.assertFalse(output.exists())
        detections.write_text('different bytes')
        self.assertEqual(self.run_cli(output,'--appearance-cache',str(path))[0],2)
        self.assertFalse(output.exists())
        detections.write_text('synthetic-source-for-cache-identity')
        connection=sqlite3.connect(path)
        connection.execute('DELETE FROM frames WHERE frame=7')
        connection.commit()
        connection.close()
        self.assertEqual(self.run_cli(output,'--appearance-cache',str(path))[0],2)
        self.assertFalse(output.exists())
        self.assertFalse(output.with_suffix('.links.jsonl').exists())

    def test_missing_cache_is_not_created(self):
        from trampoline_vision.tracking.errors import TrackingError
        missing=self.root/'does-not-exist.sqlite3'
        with self.assertRaises(TrackingError):ReadOnlyEmbeddingCache(missing,{},'fingerprint')
        self.assertFalse(missing.exists())

    def test_bad_profile_and_input_collisions_and_truncated_trace(self):
        self.assertEqual(self.run_cli(self.tracks)[0],2)
        self.assertEqual(self.run_cli(self.root/'same.json','--links-output',str(self.root/'same.json'))[0],2)
        self.assertEqual(self.run_cli(self.root/'same.json','--links-output',str(self.config))[0],2)
        value=json.loads(self.config.read_text())
        value['mode']='apply'
        self.config.write_text(json.dumps(value))
        self.assertEqual(self.run_cli(self.root/'apply.json')[0],2)
        self.set_config('geometry')
        self.tracks.write_text(''.join(json.dumps(r)+'\n' for r in self.records[:-1]))
        self.assertEqual(self.run_cli(self.root/'truncated.json')[0],2)
        self.assertFalse((self.root/'truncated.links.jsonl').exists())

    def test_publication_failure_rolls_back_own_outputs_only(self):
        output=self.root/'failure.json'
        before=self.tracks.read_bytes()
        calls=[]
        def fail_second(source,destination):
            calls.append(destination)
            if len(calls)==2:raise OSError('simulated publication failure')
            publish_exclusive(source,destination)
        with patch('trampoline_vision.application.recovery_audit.publish_exclusive',side_effect=fail_second):
            with self.assertRaises(OSError):audit_tracking_recovery(self.report,output,config_file=self.config)
        self.assertFalse(output.exists())
        self.assertFalse(output.with_suffix('.links.jsonl').exists())
        self.assertEqual(self.tracks.read_bytes(),before)

    def test_disabled_profile_keeps_baseline_without_actor_claims(self):
        self.set_config('disabled')
        output=self.root/'baseline.json'
        code,error=self.run_cli(output)
        self.assertEqual(code,0,error)
        result=json.loads(output.read_text())
        self.assertEqual(result['actor_hypotheses'],[])
        self.assertEqual(result['totals']['selected_link_proposals'],0)
        self.assertEqual(output.with_suffix('.links.jsonl').read_bytes(),b'')
