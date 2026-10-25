"""Recorregut executable després del tracking acabat, sense inferència ni solver."""

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from helpers_recovery import write_tracking_export
from trampoline_vision.application.recovery import inspect_tracking_fragments
from trampoline_vision.infrastructure.artifacts import publish_exclusive
from trampoline_vision.ingestion.video import probe_video
from trampoline_vision.interfaces.cli.main import main


@unittest.skipUnless(importlib.util.find_spec('av') and shutil.which('ffmpeg') and shutil.which('ffprobe'), 'Visualization extra and FFmpeg required')
class FragmentInspectionTests(unittest.TestCase):
    """Verifica artefactes, opcions i fallades amb un vídeo de 8 frames generat localment."""

    def setUp(self):
        """Prepara tracking amb prediccions i vídeo sense dependre de dades TFM."""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.report, self.tracks, self.video, self.records = write_tracking_export(self.root)
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=black:s=96x64:r=30',
                        '-frames:v', '8', '-c:v', 'libx264', '-bf', '0', str(self.video.path)], check=True, capture_output=True, timeout=30)
        self.inputs = {path: path.read_bytes() for path in (self.report, self.tracks, self.video.path)}

    def run_cli(self, *args):
        """Executa la CLI real i conserva stderr per interpretar errors de validació."""
        error = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(error):
            code = main(['inspect-fragments', '--tracking-report', str(self.report), *args])
        return code, error.getvalue()

    def test_cli_full_export_video_and_input_preservation(self):
        """El diagnòstic exporta fragments/buits amb IDs originals i MP4 amb tots els PTS verificats."""
        output, mp4 = self.root/'fragments.json', self.root/'fragments.mp4'
        code, error = self.run_cli('--output', str(output), '--video-output', str(mp4))
        self.assertEqual(code, 0, error)
        summary = json.loads(output.read_text())
        self.assertTrue(summary['validation']['timestamps_verified'])
        self.assertEqual(summary['totals']['fragments'], 4)
        self.assertEqual(summary['totals']['gaps'], 4)
        self.assertEqual(summary['tracking_run_id'], 'synthetic-run')
        self.assertEqual(summary['actor_reconstruction'], 'not_executed')
        blocks = [json.loads(row) for row in (self.root/'fragments.fragments.jsonl').read_text().splitlines()]
        self.assertEqual(sum(len(row['samples']) for row in blocks), 14)
        self.assertEqual(len([row for row in blocks if row['record_type'] == 'fragment']), 4)
        self.assertIn('link_proposals', summary['capabilities_not_executed'])
        for path, original in self.inputs.items():
            self.assertEqual(path.read_bytes(), original)
        code, _ = self.run_cli('--output', str(output))
        self.assertEqual(code, 2)

    def test_disabled_profile_outputs_status_and_empty_blocks(self):
        """El diagnòstic es pot desactivar sense alterar els resultats del tracker."""
        config = self.root/'disabled.json'
        config.write_text(json.dumps(dict(schema_version='1.0', task='inspect_tracking_fragments', enabled=False)))
        output = self.root/'disabled-report.json'
        code, error = self.run_cli('--output', str(output), '--config', str(config))
        self.assertEqual(code, 0, error)
        self.assertEqual(json.loads(output.read_text())['status'], 'disabled')
        self.assertEqual((self.root/'disabled-report.fragments.jsonl').read_bytes(), b'')

    def test_moved_report_paths_use_explicit_overrides(self):
        """Rutes generades dins de Docker es poden resoldre explícitament en una altra ubicació."""
        report = json.loads(self.report.read_text())
        report['inputs']['video']['path'] = '/unavailable/video.mp4'
        report['artifacts']['frames_jsonl'] = '/unavailable/tracks.jsonl'
        self.report.write_text(json.dumps(report))
        output = self.root/'moved.json'
        code, error = self.run_cli('--output', str(output), '--video', str(self.video.path), '--tracks', str(self.tracks))
        self.assertEqual(code, 0, error)

    def test_late_corruption_and_partial_report_publish_nothing(self):
        """Un fitxer tardanament corrupte no deixa artefactes presentats com a preparació completa."""
        self.tracks.write_text(''.join(json.dumps(r)+'\n' for r in self.records[:-1])+'invalid\n')
        output = self.root/'invalid.json'
        code, _ = self.run_cli('--output', str(output), '--video-output', str(self.root/'invalid.mp4'))
        self.assertEqual(code, 2)
        self.assertFalse(output.exists())
        self.assertFalse((self.root/'invalid.fragments.jsonl').exists())
        self.assertFalse((self.root/'invalid.mp4').exists())
        self.tracks.write_bytes(self.inputs[self.tracks])
        report = json.loads(self.report.read_text())
        report['range']['last_frame_index'] = 6
        self.report.write_text(json.dumps(report))
        code, _ = self.run_cli('--output', str(output))
        self.assertEqual(code, 2)
        self.assertFalse(output.exists())

    def test_collisions_and_declared_hash_mismatch_are_rejected(self):
        """Les sortides no poden substituir entrades, configuracions o noms existents."""
        code, _ = self.run_cli('--output', str(self.report))
        self.assertEqual(code, 2)
        code, _ = self.run_cli('--output', str(self.root/'same.json'), '--fragments-output', str(self.root/'same.json'))
        self.assertEqual(code, 2)
        report = json.loads(self.report.read_text())
        report['inputs']['video']['sha256'] = '0'*64
        self.report.write_text(json.dumps(report))
        code, error = self.run_cli('--output', str(self.root/'hash.json'))
        self.assertEqual(code, 2)
        self.assertIn('content hash', error)
        self.assertFalse((self.root/'hash.json').exists())

    def test_publication_failure_removes_only_own_new_artifacts(self):
        """Una fallada en publicar l'informe neteja l'exportació nova, preservant les entrades."""
        output = self.root/'failed.json'
        calls = []

        def fail_second(source, destination):
            """Publica el primer artefacte real i simula un error de disc al següent."""
            calls.append(destination)
            if len(calls) == 2:
                raise OSError('simulated publication failure')
            publish_exclusive(source, destination)

        with patch('trampoline_vision.application.recovery.publish_exclusive', side_effect=fail_second):
            with self.assertRaises(OSError):
                inspect_tracking_fragments(self.report, output)
        self.assertFalse(output.exists())
        self.assertFalse((self.root/'failed.fragments.jsonl').exists())
        self.assertEqual(self.tracks.read_bytes(), self.inputs[self.tracks])

    def test_variable_frame_timing_is_preserved(self):
        """El renderer i la fragmentació suporten VFR sense assumir intervals constants."""
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=black:s=96x64:r=30',
                        '-frames:v', '8', '-vf', "setpts='if(lt(N,4),N,N+2)'", '-fps_mode', 'vfr',
                        '-c:v', 'libx264', '-bf', '0', str(self.video.path)], check=True, capture_output=True, timeout=30)
        video = probe_video(self.video.path, 'boxes')
        self.report, self.tracks, _, _ = write_tracking_export(self.root, timestamps=video.timestamps_s)
        output, mp4 = self.root/'vfr.json', self.root/'vfr.mp4'
        code, error = self.run_cli('--output', str(output), '--video-output', str(mp4))
        self.assertEqual(code, 0, error)
        self.assertTrue(json.loads(output.read_text())['validation']['timestamps_verified'])

    def test_draft_profiles_remain_unexecutable(self):
        """Els perfils d'associació futura no activen un solver ni s'ignoren silenciosament."""
        config = self.root/'draft.json'
        config.write_text(json.dumps(dict(schema_version='0.1-draft', implementation_status='design-only', enabled=True)))
        code, _ = self.run_cli('--output', str(self.root/'draft-output.json'), '--config', str(config))
        self.assertEqual(code, 2)
        self.assertFalse((self.root/'draft-output.json').exists())
