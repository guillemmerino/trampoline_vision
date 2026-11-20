"""Controls de seguretat del replay d'identitat, sense executar la bateria."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmarks.calibration.tools import identity_comparison as study


class IdentityComparisonTests(unittest.TestCase):
    """Protegeix el preflight i la igualtat de les entrades aparellades."""

    def write_traces(self, folder, *, changed=None, extra=False):
        """Crea traces mínimes amb una candidata i diferències deliberades."""
        candidate = {'candidate_id': '0:c:1', 'measurement': {'score': .4}}
        (folder/'preparation.jsonl').write_text(json.dumps({'candidates': [candidate]})+'\n')
        for name in study.PROFILES:
            value = {**candidate, 'provenance': [], 'unassigned_reason': 'unconfirmed_or_unmatched'}
            if name == changed:
                value['measurement'] = {'score': .5}
            row = {'context': {'frame_index': 0}, 'candidates': [value]}
            text = json.dumps(row)+'\n'
            if extra and name == 'botsort-reid':
                text += text
            (folder/f'{name}.frames.jsonl').write_text(text)

    def test_same_candidates_allow_different_assignment_metadata(self):
        """L'associació pot variar sense alterar l'entrada comuna."""
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            self.write_traces(folder)
            study.compare_candidates(folder, 1)

    def test_different_input_blocks_completion(self):
        """Una confiança alterada no pot publicar una comparació aparellada."""
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            self.write_traces(folder, changed='botsort-reid')
            with self.assertRaisesRegex(ValueError, 'input differs'):
                study.compare_candidates(folder, 1)

    def test_extra_frames_block_completion(self):
        """Una traça més llarga no queda validada pel prefix compartit."""
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            self.write_traces(folder, extra=True)
            with self.assertRaisesRegex(ValueError, 'Extra frames'):
                study.compare_candidates(folder, 1)

    def test_default_preflight_never_creates_run(self):
        """La comanda per defecte no entra al cas d'ús ni crea el destí."""
        cases = [(None, type('Video', (), {'frame_count': 870})(), None, None)]*3
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'must-not-exist'
            with patch.object(study, 'resolve', return_value=(None, {}, cases, {'plan_sha256': 'test'})), \
                    patch.object(study, 'environment', return_value={}), redirect_stdout(io.StringIO()) as stream:
                self.assertEqual(study.main(['--output', str(output)]), 0)
            self.assertFalse(output.exists())
            self.assertFalse(json.loads(stream.getvalue())['tracking_executed'])


if __name__ == '__main__':
    unittest.main()
