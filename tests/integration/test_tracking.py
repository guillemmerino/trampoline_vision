"""Proves del backend i recorregut instal·lable amb vídeos generats, mai el clip real de TFM."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from helpers import make_case
from helpers_tracking import pose_values, tracking_frame
from trampoline_vision.application.tracking import track_case
from trampoline_vision.ingestion.manifest import load_manifest
from trampoline_vision.ingestion.tracking_config import load_tracking_config
from trampoline_vision.ingestion.video import probe_video
from trampoline_vision.interfaces.cli.main import main
from trampoline_vision.tracking.config import TrackerConfig
from trampoline_vision.tracking.session import TrackingSession
from trampoline_vision.infrastructure.artifacts import publish_exclusive


@unittest.skipUnless(importlib.util.find_spec("trackers"), "Tracking extra required")
class TrackingBackendIntegrationTests(unittest.TestCase):
    """Contrasta les transicions pròpies amb l'API pública real de la biblioteca fixada."""

    def test_recovery_and_expiration_with_irregular_times(self):
        """Conserva ID en una absència curta i n'assigna un de nou quan supera el pressupost temporal."""
        session = TrackingSession(TrackerConfig(confirmation_frames=1, max_lost_s=.3), 25)
        for i, timestamp in enumerate((0, .04, .09)):
            result = session.update(tracking_frame(i, timestamp))
        identity = result.tracks[0].track_id
        result = session.update(tracking_frame(3, .13, (), "missing"))
        self.assertEqual(result.tracks[0].state, "lost")
        result = session.update(tracking_frame(4, .18))
        self.assertEqual(result.tracks[0].track_id, identity)
        self.assertEqual([e.kind for e in session.events], ["recovered"])
        result = session.update(tracking_frame(5, 1, ()))
        self.assertEqual(result.tracks[0].state, "finished")
        session.update(tracking_frame(6, 1.04))
        result = session.update(tracking_frame(7, 1.09))
        self.assertNotEqual(result.tracks[0].track_id, identity)

    def test_large_timestamp_gap_cannot_revive_expired_id(self):
        """Un buit gran entre dos fotogrames, sense instants intermedis inventats, força una nova identitat."""
        session = TrackingSession(TrackerConfig(confirmation_frames=1, max_lost_s=.1), 25)
        session.update(tracking_frame())
        first = session.update(tracking_frame(1, .04)).tracks[0].track_id
        result = session.update(tracking_frame(2, 1.0))
        self.assertTrue(any(t.track_id == first and t.state == "finished" for t in result.tracks))
        result = session.update(tracking_frame(3, 1.04))
        self.assertNotEqual(result.tracks[0].track_id, first)

    def test_default_confirmation_has_no_hidden_associations_after_a_miss(self):
        """Regressió real del cas 0.3.0: amb naixements a 3, les mesures 7 i 8 ja són observades després del buit 6."""
        session = TrackingSession(TrackerConfig(confirmation_frames=3), 30)
        results = []
        for i in range(10):
            results.append(session.update(tracking_frame(i, i / 30, () if i == 6 else ("a",))))
        self.assertEqual(results[0].tracks, ())
        self.assertEqual(results[1].tracks, ())
        self.assertEqual(results[2].tracks, ())
        self.assertEqual(results[3].tracks[0].evidence, "observed")
        identity = results[5].tracks[0].track_id
        self.assertEqual(results[6].tracks[0].evidence, "predicted")
        for i in (7, 8, 9):
            self.assertEqual(results[i].tracks[0].track_id, identity)
            self.assertEqual(results[i].tracks[0].evidence, "observed")
            self.assertAlmostEqual(results[i].tracks[0].last_observed_timestamp_s, i / 30)
            self.assertEqual(results[i].unassigned_candidate_ids, ())


@unittest.skipUnless(importlib.util.find_spec("trackers") and importlib.util.find_spec("av") and shutil.which("ffmpeg") and shutil.which("ffprobe"),
                     "Tracking Docker image with FFmpeg and visualization required")
class TrackingPipelineIntegrationTests(unittest.TestCase):
    """Comprova CLI, interval, artefactes i fallades abans de publicar resultats."""

    def setUp(self):
        """Construeix vuit fotogrames a 10 FPS amb una absència curta de JSON i configuració executable."""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        video = self.root / "video.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x48:r=10:d=0.8",
                        "-c:v", "libx264", "-bf", "0", str(video)], check=True, capture_output=True, timeout=30)
        person = {"pose_keypoints_2d": pose_values()}
        self.records = {f"frame_{i + 1:06d}_keypoints.json": {"people": [person]} for i in range(8) if i != 3}
        self.manifest_path = make_case(self.root, self.records)
        self.prep = self.root / "preparation.json"
        self.prep.write_text(json.dumps({"schema_version": "1.0"}))
        self.config = self.root / "pipeline.json"
        self.config.write_text(json.dumps({"schema_version": "1.0", "task": "track_recorded_detections",
                                           "case_manifest": self.manifest_path.name, "preparation_config": self.prep.name,
                                           "tracker": {"confirmation_frames": 1}}))

    def run_cli(self, *args):
        """Captura terminal i executa la CLI real sense obrir finestres ni publicar fora del temporal."""
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return main(["track", "--config", str(self.config), *args])

    def test_cli_full_jsonl_and_video_preserve_time_and_recovery(self):
        """Genera MP4 verificat i JSONL amb ID estable abans/després del buit i l'últim fotograma."""
        report, video = self.root / "report.json", self.root / "review.mp4"
        self.assertEqual(self.run_cli("--output", str(report), "--video-output", str(video)), 0)
        summary = json.loads(report.read_text())
        frames = [json.loads(line) for line in (self.root / "report.frames.jsonl").read_text().splitlines()]
        self.assertEqual(len(frames), 8)
        self.assertEqual(frames[3]["source_status"], "missing")
        self.assertEqual(frames[3]["tracks"][0]["evidence"], "predicted")
        self.assertEqual(frames[2]["tracks"][0]["track_id"], frames[4]["tracks"][0]["track_id"])
        self.assertEqual(frames[-1]["context"]["frame_index"], 7)
        self.assertTrue(summary["validation"]["timestamps_verified"])
        self.assertEqual(summary["output_video"]["frame_count"], 8)
        self.assertEqual(summary["events_in_selected_range"]["recovered"], 1)
        self.assertEqual(len(summary["right_censored_track_ids"]), 1)
        self.assertEqual(self.run_cli("--output", str(report)), 2)

    @unittest.skipUnless(importlib.util.find_spec("cv2"), "Silhouette preparation requires OpenCV")
    def test_representative_profile_in_video_and_trace_only_modes(self):
        """Both decoding paths select the same candidate boxes from an explicit profile."""
        boxes = self.root / "boxes.csv"
        rows = ["frame,det_id,x1,y1,x2,y2,conf,class_id"]
        for i in range(8):
            rows += [f"{i},0,22,10,40,38,0.8,0", f"{i},1,1,1,10,10,0.9,0"]
        boxes.write_text("\n".join(rows) + "\n")
        manifest = self.root / "box-case.json"
        manifest.write_text(json.dumps({"schema_version": "1.0", "path_base": "manifest_directory",
            "case_id": "representative", "video": {"path": "video.mp4"}, "detections": {"primary": {
                "path": boxes.name, "format": "person_boxes_csv", "frame_index_base": 0,
                "coordinate_space": "original_frame_pixels", "frame_coverage": "complete_video"}}}))
        self.prep.write_text(json.dumps({"schema_version": "1.0", "box_preparation": {"enabled": True},
            "representative_boxes": {"zone": [.24, .15, .85, .9], "zone_mode": "hard", "max_candidates": 12}}))
        pipeline = json.loads(self.config.read_text())
        pipeline["case_manifest"] = manifest.name
        self.config.write_text(json.dumps(pipeline))
        for suffix, args in (("plain", ()), ("overlay", ("--video-output", str(self.root / "prepared.mp4")))):
            report = self.root / (suffix + ".json")
            self.assertEqual(self.run_cli("--output", str(report), *args), 0)
            info = json.loads(report.read_text())
            self.assertEqual(info["preparation_background"]["sample_frame_indices"], list(range(8)))
            self.assertEqual(info["totals"]["candidates"], 8)
            self.assertEqual(info["totals"]["source_detections"], 16)
            frames = [json.loads(line) for line in report.with_suffix(".frames.jsonl").read_text().splitlines()]
            self.assertTrue(all(f["candidates"][0]["measurement"]["bbox"]["x_min"] == 22 for f in frames))

    def test_partial_run_uses_warmup_and_preserves_original_timestamps(self):
        """El tall no reinicia el tracker a mig vídeo ni canvia el temps original del JSONL."""
        output = self.root / "part.json"
        self.assertEqual(self.run_cli("--output", str(output), "--start", "0.4", "--end", "0.7"), 0)
        summary = json.loads(output.read_text())
        frames = [json.loads(line) for line in (self.root / "part.frames.jsonl").read_text().splitlines()]
        self.assertEqual(summary["range"]["warmup_frames"], 4)
        self.assertEqual([f["context"]["frame_index"] for f in frames], [4, 5, 6])
        self.assertEqual(frames[0]["context"]["timestamp_s"], .4)
        self.assertEqual(frames[0]["events"][0]["kind"], "recovered")

    def test_variable_frame_times_are_preserved_in_tracking_video(self):
        """L'exportació de seguiment tampoc força 10 FPS si els temps de presentació són irregulars."""
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x48:r=10:d=0.8",
                        "-vf", "setpts='if(lt(N,4),N,N+2)'", "-fps_mode", "vfr", "-c:v", "libx264", "-bf", "0",
                        str(self.root / "video.mp4")], check=True, capture_output=True, timeout=30)
        output = self.root / "vfr.json"
        self.assertEqual(self.run_cli("--output", str(output), "--video-output", str(self.root / "vfr.mp4")), 0)
        summary = json.loads(output.read_text())
        self.assertTrue(summary["validation"]["timestamps_verified"])
        self.assertEqual(summary["output_video"]["frame_count"], 8)

    def test_corrupt_last_record_does_not_publish_partial_outputs(self):
        """Una entrada corrupta tardana invalida tota la publicació, encara que ja hi hagi tracks temporals."""
        self.records["frame_000008_keypoints.json"] = "invalid"
        make_case(self.root, self.records)
        output = self.root / "bad.json"
        self.assertEqual(self.run_cli("--output", str(output), "--video-output", str(self.root / "bad.mp4")), 2)
        self.assertFalse(output.exists())
        self.assertFalse((self.root / "bad.frames.jsonl").exists())
        self.assertFalse((self.root / "bad.mp4").exists())

    def test_publish_race_rolls_back_only_outputs_created_by_this_run(self):
        """Si un altre procés ocupa l'informe al final, es conserva aquest fitxer i es retira el JSONL propi."""
        manifest = load_manifest(self.manifest_path)
        video = probe_video(manifest.video_path, manifest.case_id)
        output, frames = self.root / "race.json", self.root / "race.jsonl"

        def race(staged, destination):
            """Simula un destí creat després de validar rutes, just abans de publicar l'informe."""
            if destination == output:
                output.write_bytes(b"other process")
            publish_exclusive(staged, destination)

        with patch("trampoline_vision.application.tracking.publish_exclusive", side_effect=race):
            with self.assertRaises(FileExistsError):
                track_case(manifest, video, output, frames, tracker=TrackerConfig(confirmation_frames=1))
        self.assertEqual(output.read_bytes(), b"other process")
        self.assertFalse(frames.exists())

    def test_configuration_unknown_fields_are_errors(self):
        """Una errada de configuració no es resol silenciosament amb un llindar diferent."""
        value = json.loads(self.config.read_text())
        value["tracker"]["confidence_typo"] = .01
        self.config.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            load_tracking_config(self.config)
