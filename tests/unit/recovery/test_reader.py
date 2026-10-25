"""Rebuig de traces parcials, barrejades o incoherents abans de fragmentar."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from helpers_recovery import write_tracking_export
from trampoline_vision.ingestion.recovery import load_tracking_trace
from trampoline_vision.recovery.errors import RecoveryError


class TrackingTraceReaderTests(unittest.TestCase):
    """Contrasta contingut i metadades amb timeline original, inclosa corrupció tardana."""

    def setUp(self):
        """Prepara artefactes sintètics complets amb diversos estats de vida."""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.report, self.tracks, self.video, self.records = write_tracking_export(self.root)

    def write(self, records):
        """Publica una variant de la mateixa traça perquè el lector real la validi."""
        self.tracks.write_text(''.join(json.dumps(row)+'\n' for row in records), encoding='utf-8')

    def test_full_trace_keeps_measurements_predictions_and_hashes(self):
        """El resultat de lectura no descarta frames sense deteccions ni estat finished."""
        loaded = load_tracking_trace(self.tracks, self.report, self.video)
        self.assertEqual(len(loaded.trace.frames), 8)
        self.assertEqual(loaded.trace.frames[3].tracks[0].evidence, 'predicted')
        self.assertEqual(len(loaded.frames_sha256), 64)
        self.assertEqual(loaded.trace.frames[0].candidates[0].candidate.measurement.score, .9)

    def test_truncated_extra_and_partial_exports_are_refused(self):
        """El recompte del report no substitueix comprovar el JSONL complet fins a EOF."""
        for records in (self.records[:-1], self.records+[self.records[-1]], self.records[1:]):
            self.write(records)
            with self.assertRaises(RecoveryError):
                load_tracking_trace(self.tracks, self.report, self.video)
        self.write(self.records)
        report = json.loads(self.report.read_text())
        report['range']['first_frame_index'] = 1
        self.report.write_text(json.dumps(report))
        with self.assertRaisesRegex(RecoveryError, 'complete tracking'):
            load_tracking_trace(self.tracks, self.report, self.video)

    def test_bad_identity_partition_geometry_provenance_and_time_are_refused(self):
        """Ni un run diferent ni una assignació inconsistent es converteixen en fragments vàlids."""
        changes = [lambda row: row.update(run_id='other'),
                   lambda row: row['context'].update(frame_index=2),
                   lambda row: row['context'].update(timestamp_s=.01),
                   lambda row: row['context'].update(width_px=True),
                   lambda row: row.update(unassigned_candidate_ids=[row['candidates'][0]['candidate_id']]),
                   lambda row: row['tracks'][0]['bbox'].update(x_min=6),
                   lambda row: row['candidates'][0].update(provenance=[]),
                   lambda row: row['events'].clear()]
        for change in changes:
            records = deepcopy(self.records)
            change(records[0])
            self.write(records)
            with self.subTest(change=change), self.assertRaises(RecoveryError):
                load_tracking_trace(self.tracks, self.report, self.video)

    def test_lifecycle_resurrection_and_forged_prediction_timestamp_are_refused(self):
        """Els buits no poden adquirir una mesura nova i un track retirat no pot tornar a aparèixer."""
        records = deepcopy(self.records)
        records[2]['tracks'][0]['last_observed_timestamp_s'] = 0
        self.write(records)
        with self.assertRaisesRegex(RecoveryError, 'last observation'):
            load_tracking_trace(self.tracks, self.report, self.video)
        records = deepcopy(self.records)
        sample = deepcopy(records[0]['tracks'][1])
        sample.update(state='lost', evidence='predicted', candidate_id=None)
        records[-1]['tracks'].append(sample)
        self.write(records)
        with self.assertRaisesRegex(RecoveryError, 'reappeared'):
            load_tracking_trace(self.tracks, self.report, self.video)

    def test_duplicate_keys_nonfinite_and_late_corruption_are_refused(self):
        """JSON estricte també al darrer registre; no s'amaga corrupció com a frame buit."""
        for bad in ('{"run_id":"a","run_id":"b"}', '{"value":NaN}', 'invalid', ''):
            self.write(self.records[:-1])
            with self.tracks.open('a', encoding='utf-8') as stream:
                stream.write(bad+'\n')
            with self.subTest(bad=bad), self.assertRaises(RecoveryError):
                load_tracking_trace(self.tracks, self.report, self.video)

    def test_report_counts_censoring_and_checksum_are_checked(self):
        """L'informe i la traça han de descriure la mateixa execució i evidència."""
        original = json.loads(self.report.read_text())
        for change in (lambda r: r['totals'].update(observed_track_samples=999),
                       lambda r: r.update(right_censored_track_ids=[]),
                       lambda r: r['artifacts'].update(frames_sha256='0'*64)):
            report = deepcopy(original)
            change(report)
            self.report.write_text(json.dumps(report))
            with self.assertRaises(RecoveryError):
                load_tracking_trace(self.tracks, self.report, self.video)

    def test_unmeasurable_candidates_and_missing_frames_remain_explicit(self):
        """La preparació conserva també evidència parcial sense caixa, en lloc de descartar-la."""
        records = deepcopy(self.records)
        provenance = deepcopy(records[0]['candidates'][0]['provenance'])
        provenance[0]['source_person_index'] = 99
        records[0]['candidates'].append({'candidate_id': '0:partial', 'source_detection_ids': ['0:source:99'],
            'measurement': None, 'issues': ['insufficient_geometry'], 'provenance': provenance, 'unassigned_reason': 'no_measurement'})
        records[0]['source_detections'] += 1
        records[0]['unassigned_candidate_ids'].append('0:partial')
        records[3]['source_status'] = 'missing'
        self.write(records)
        loaded = load_tracking_trace(self.tracks, self.report, self.video)
        partial = loaded.trace.frames[0].candidates[-1]
        self.assertIsNone(partial.candidate.measurement)
        self.assertEqual(partial.unassigned_reason, 'no_measurement')
        self.assertEqual(loaded.trace.frames[3].source_status, 'missing')
        self.assertEqual(loaded.trace.frames[3].tracks[0].evidence, 'predicted')
