"""Comprova els buits, el context posterior i els empats del graf experimental."""

import unittest
from importlib.util import find_spec


@unittest.skipUnless(find_spec('numpy'), 'El graf experimental requereix NumPy')
class SubjectPathTest(unittest.TestCase):
    """Exerceix les decisions que un únic camí òptim podria amagar."""

    def solve(self, frames, max_missing=5):
        """Converteix els centres petits de prova i resol des de l’única caixa inicial."""
        from trampoline_vision.recovery.subject_path import SubjectCandidate, SubjectPathConfig, TemporalGraph

        config = SubjectPathConfig(.12, .5, .12, .06, .68, max_missing, .08)
        rows = [[SubjectCandidate(i, name, tid, x, y, scale) for name, tid, x, y, scale in row]
                for i, row in enumerate(frames)]
        return TemporalGraph(rows, 0, rows[0][0].candidate_id, config).solve()

    def test_future_evidence_reconnects_after_a_gap(self):
        """Les caixes posteriors afavoreixen una reaparició amb un altre ID."""
        frames = [
            [('a', '92', 0, 9, 1)],
            [('a', '92', 0, 8, 1)],
            [('a', '92', 0, 7, .9)],
            [('a', '92', 0, 6, .85)],
            [('b', '50', 4, 6, 1)],
            [('b', '50', 4, 6, 1)],
            [('b', '92', 0, 3, 1), ('c', '44', 0, 2.2, 1.1)],
            [('c', '44', 0, .5, 1)],
            [('c', '44', 0, -1.2, 1)],
        ]
        path = self.solve(frames)
        self.assertEqual(sorted(path.observations), [0, 1, 2, 3, 6, 7, 8])
        self.assertEqual(path.observations[6].track_id, '44')
        self.assertAlmostEqual(path.gap_costs[4], path.cost)
        self.assertLess(path.candidate_costs[6]['c'], path.candidate_costs[6]['b'])

    def test_reports_both_candidates_in_a_tie(self):
        """Dues hipòtesis simètriques es conserven amb el mateix cost global."""
        path = self.solve([
            [('a', '1', 0, 0, 1)],
            [('left', '2', -.1, 1, 1), ('right', '3', .1, 1, 1)],
            [('after', '4', 0, 2, 1)],
        ])
        self.assertAlmostEqual(path.candidate_costs[1]['left'], path.cost)
        self.assertAlmostEqual(path.candidate_costs[1]['right'], path.cost)
        self.assertGreater(path.gap_costs[1], path.cost)

    def test_gap_limit_preserves_unreachable_candidates(self):
        """Una reaparició fora de l’horitzó queda com a buit en el graf."""
        path = self.solve([[('a', None, 0, 0, 1)], [], [], [('b', None, 0, 0, 1)]], max_missing=1)
        self.assertEqual(set(path.observations), {0})
        self.assertNotIn(3, path.candidate_costs)
        self.assertAlmostEqual(path.gap_costs[3], path.cost)
