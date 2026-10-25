"""Recorregut CLI de caixes enregistrades amb vídeo sintètic i canvi de perfil."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from importlib import util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from trampoline_vision.application.tracking import track_case
from trampoline_vision.ingestion.manifest import load_manifest
from trampoline_vision.ingestion.video import probe_video
from trampoline_vision.interfaces.cli.main import main
from trampoline_vision.tracking.config import TrackerConfig
from trampoline_vision.tracking.errors import TrackingError


@unittest.skipUnless(util.find_spec('trackers') and util.find_spec('av') and shutil.which('ffmpeg'), 'Tracking and visualization extras required')
class BoxPipelineTests(unittest.TestCase):
    """Valida l'ús públic del paquet; no requereix vídeos, anotacions ni pesos de TFM."""

    def setUp(self):
        """Genera 10 frames, un CSV complet i un pipeline amb perfil referenciat."""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=black:s=96x64:r=10:d=1', '-c:v', 'libx264', '-bf', '0', str(self.root/'video.mp4')], check=True, capture_output=True, timeout=30)
        (self.root/'boxes.csv').write_text('frame,det_id,x1,y1,x2,y2,conf,class_id\n' + ''.join(f'{i},0,5,5,20,45,.9,0\n' for i in range(10) if i != 5))
        manifest = dict(schema_version='1.0', path_base='manifest_directory', case_id='synthetic', video={'path': 'video.mp4'},
            detections={'primary': dict(path='boxes.csv', format='person_boxes_csv', frame_index_base=0, coordinate_space='original_frame_pixels', frame_coverage='complete_video')})
        self.manifest_path = self.root/'case.json'
        self.manifest_path.write_text(json.dumps(manifest))
        self.pipeline = self.root/'pipeline.json'
        self.pipeline.write_text(json.dumps(dict(schema_version='2.0', task='track_recorded_detections', case_manifest='case.json', tracker_config='tracker.json')))

    def test_change_one_profile_runs_each_motion_backend_with_verified_overlay(self):
        """La mateixa entrada funciona en tots els backends; només varia tracker.json."""
        names = ['ocsort', 'bytetrack'] + (['botsort'] if util.find_spec('boxmot') else [])
        for name in names:
            with self.subTest(backend=name):
                (self.root/'tracker.json').write_text(json.dumps(dict(schema_version='2.0', backend=name, lifecycle={'confirmation_frames': 1})))
                report = self.root/f'{name}.json'
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    code = main(['track', '--config', str(self.pipeline), '--output', str(report), '--video-output', str(self.root/f'{name}.mp4')])
                self.assertEqual(code, 0)
                result = json.loads(report.read_text())
                self.assertEqual(result['backend']['name'], name)
                self.assertEqual(result['totals']['source_detections'], 9)
                self.assertTrue(result['validation']['timestamps_verified'])
                self.assertEqual(result['events_in_selected_range']['recovered'], 1)
                frames = [json.loads(line) for line in (self.root/f'{name}.frames.jsonl').read_text().splitlines()]
                self.assertEqual(frames[5]['tracks'][0]['evidence'], 'predicted')
                self.assertEqual(frames[4]['tracks'][0]['track_id'], frames[6]['tracks'][0]['track_id'])

    def test_botsort_rejects_variable_timing_before_creating_outputs(self):
        """El límit temporal de BoxMOT s'exposa com a error d'entrada, sense retenció simulada."""
        manifest = load_manifest(self.manifest_path)
        video = probe_video(manifest.video_path, manifest.case_id)
        video = replace(video, timestamps_s=tuple(t + (.1 if i >= 5 else 0) for i, t in enumerate(video.timestamps_s)), frame_durations_s=(.1,)*4 + (.2,) + (.1,)*5)
        report = self.root/'invalid.json'
        with self.assertRaisesRegex(TrackingError, 'constant frame timing'):
            track_case(manifest, video, report, self.root/'invalid.jsonl', tracker=TrackerConfig(backend='botsort'))
        self.assertFalse(report.exists())
