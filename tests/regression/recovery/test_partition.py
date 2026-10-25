"""Regressió de partició i determinisme amb diverses identitats i buits irregulars."""

from pathlib import Path
import random
import unittest

from helpers_recovery import records_and_video, trace_from_records
from trampoline_vision.recovery.pipeline import prepare_recovery


class FragmentPartitionRegressionTests(unittest.TestCase):
    """Exerceix ratxes curtes/llargues i pèrdues concurrents sense pesos ni algoritmes visuals."""

    def test_randomized_missing_runs_preserve_original_samples_and_deterministic_ids(self):
        """El mateix tracking sempre produeix els mateixos fragments sense perdre o duplicar evidència."""
        rng = random.Random(1081)
        pattern, times = [{0: 'observed', 1: 'observed', 2: 'observed'}], [0.]
        for index in range(1, 100):
            pattern.append({tid: ('observed' if rng.random() > .3 else 'lost') for tid in range(3)})
            times.append(times[-1] + rng.choice((.02, .04, .09)))
        records, video = records_and_video(Path('/synthetic'), pattern, times)
        trace = trace_from_records(records, video)
        first, second = prepare_recovery(trace), prepare_recovery(trace)
        self.assertEqual(first, second)
        self.assertEqual(sum(len(f.samples) for f in first.fragments), sum(s.evidence == 'observed' for f in trace.frames for s in f.tracks))
        self.assertEqual(sum(len(g.samples) for g in first.gaps), sum(s.evidence == 'predicted' for f in trace.frames for s in f.tracks))
        self.assertTrue(all(f.track_id == f.samples[0].track.track_id for f in first.fragments))
