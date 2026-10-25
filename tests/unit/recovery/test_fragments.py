"""Fragmentació i partició d'evidència amb pèrdues, recuperacions i finalització explícites."""

from dataclasses import replace
from pathlib import Path
import unittest

from helpers_recovery import records_and_video, trace_from_records
from trampoline_vision.contracts.recovery import TrajectoryFragment, FragmentLink
from trampoline_vision.recovery.config import FragmentationConfig
from trampoline_vision.recovery.errors import RecoveryError
from trampoline_vision.recovery.pipeline import prepare_recovery
from trampoline_vision.recovery.validation import validate_fragmentation
from trampoline_vision.results.recovery import diagnostics, fragment_record, sample_labels


class FragmentationTests(unittest.TestCase):
    """Evita donar continuïtat observada a prediccions o perdre l'evidència original."""

    def setUp(self):
        """Tres tracks amb quatre ratxes observades i diferents tipus de buit."""
        records, video = records_and_video(Path('/synthetic'))
        self.trace = trace_from_records(records, video)
        self.result = prepare_recovery(self.trace)

    def test_fragments_and_gaps_preserve_every_sample(self):
        """Cada observació entra en una ratxa i cada predicció/finished en un buit, exactament una vegada."""
        self.assertEqual([(f.track_id, [s.context.frame_index for s in f.samples], f.start_reason, f.end_reason) for f in self.result.fragments],
            [('ocsort:0', [0, 1], 'confirmed', 'lost'), ('ocsort:0', [4, 5], 'recovered', 'finished'),
             ('ocsort:1', [0, 1, 2], 'confirmed', 'finished'), ('ocsort:2', [5], 'confirmed', 'lost')])
        gaps0 = [g for g in self.result.gaps if g.track_id == 'ocsort:0']
        self.assertEqual(gaps0[0].next_fragment_id, self.result.fragments[1].fragment_id)
        self.assertEqual([s.context.frame_index for s in gaps0[0].samples], [2, 3])
        self.assertIsNone(gaps0[0].samples[-1].track.bbox)
        self.assertEqual(gaps0[1].end_reason, 'finished')
        self.assertEqual(self.result.gaps[-1].end_reason, 'video_end')
        summary = diagnostics(self.result)
        self.assertEqual(summary['totals']['observed_samples'], 8)
        self.assertEqual(summary['totals']['lost_samples'], 4)
        self.assertEqual(summary['totals']['finished_samples'], 2)
        self.assertEqual(summary['actor_reconstruction'], 'not_executed')

    def test_vfr_uses_original_time_and_observed_duration(self):
        """Cap velocitat ni durada es calcula assumint FPS constants."""
        records, video = records_and_video(Path('/synthetic'), timestamps=(0., .04, .11, .14, .22, .25, .4, .47))
        result = prepare_recovery(trace_from_records(records, video))
        first = fragment_record(result.fragments[0])
        self.assertAlmostEqual(first['observed_duration_s'], .11)
        self.assertEqual(first['samples'][1]['context']['timestamp_s'], .04)
        self.assertEqual(result.gaps[0].samples[0].context.timestamp_s, .11)

    def test_disabled_preparation_retains_exact_trace_and_no_fragments(self):
        """L'opció disabled no crea unions, fragments ni una falsa reconstrucció."""
        result = prepare_recovery(self.trace, FragmentationConfig(enabled=False))
        self.assertIs(result.trace, self.trace)
        self.assertEqual((result.fragments, result.gaps), ((), ()))
        self.assertEqual(diagnostics(result, enabled=False)['status'], 'disabled')

    def test_no_actors_and_right_censored_observed_track_are_valid(self):
        """Un vídeo sense tracks i una ratxa viva a l'últim frame no es finalitzen artificialment."""
        for pattern in ([{}, {}], [{0: 'observed'}]):
            records, video = records_and_video(Path('/synthetic'), pattern)
            result = prepare_recovery(trace_from_records(records, video))
            self.assertEqual(len(result.fragments), bool(pattern[0]))
            if result.fragments:
                self.assertEqual(result.fragments[0].end_reason, 'video_end')

    def test_validation_detects_missing_samples_and_wrong_gap_links(self):
        """La partició ha de cobrir tot el tracking i els buits han de referenciar trams compatibles."""
        with self.assertRaises(RecoveryError):
            validate_fragmentation(replace(self.result, fragments=self.result.fragments[1:]))
        gap = replace(self.result.gaps[0], previous_fragment_id='unknown')
        with self.assertRaises(RecoveryError):
            validate_fragmentation(replace(self.result, gaps=(gap, *self.result.gaps[1:])))

    def test_source_provenance_and_labels_remain_accessible(self):
        """Cada mostra es pot tornar a relacionar amb el candidat i la seva fila d'entrada."""
        first = self.result.fragments[0].samples[0]
        self.assertEqual(first.candidate.provenance[0].source_path, 'synthetic.csv')
        self.assertEqual(first.candidate.candidate.source_detection_ids, ('0:box:0',))
        labels = sample_labels(self.result)
        self.assertIsNone(labels[(0, 'ocsort:0')][1])
        self.assertIsNotNone(labels[(2, 'ocsort:0')][1])
        with self.assertRaises(ValueError):
            TrajectoryFragment('invalid', 'ocsort:0', (first, self.result.fragments[1].samples[0]), 'confirmed', 'video_end')

    def test_future_link_contract_keeps_ambiguity_and_rejects_invalid_evidence(self):
        """Es pot representar pending sense probabilitats inventades ni cap solver executat."""
        link = FragmentLink('a', 'b', 'pending', (('motion', .2),), ('competing_candidates',))
        self.assertEqual(link.status, 'pending')
        for args in [('a', 'a', 'accepted'), ('a', 'b', 'unknown')]:
            with self.assertRaises(ValueError):
                FragmentLink(*args)
        with self.assertRaises(ValueError):
            FragmentLink('a', 'b', 'pending', (('motion', float('nan')),))

    def test_only_executable_fragmentation_profiles_are_accepted(self):
        """Els esborranys d'unió i els llindars encara no implementats no es consumeixen silenciosament."""
        for value in [dict(schema_version='0.1-draft', enabled=True),
                      dict(schema_version='1.0', task='inspect_tracking_fragments', strategy='hungarian'),
                      dict(schema_version='1.0', task='inspect_tracking_fragments', enabled=1),
                      dict(schema_version='1.0', task='inspect_tracking_fragments', policy='merge_all')]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                FragmentationConfig.from_dict(value)
