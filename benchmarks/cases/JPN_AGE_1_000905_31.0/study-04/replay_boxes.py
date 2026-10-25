"""Reprodueix caixes YOLO enregistrades, sense passar retalls ni articulacions al tracker.

És un experiment aïllat sobre el paquet 0.4.0. Les 25 articulacions del
contenidor canònic són absents explícites: cap coordenada de pose es fabrica.
No s'executa YOLO/OpenPose ni s'utilitza det_id com a identitat temporal.
"""

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
import csv
import hashlib
import json
import math
from pathlib import Path
import sys
from uuid import uuid4

from trampoline_vision import __version__
from trampoline_vision.contracts.observations import (
    BODY25_NAMES, DetectionProvenance, FrameDetections, KeypointObservation, PersonDetection,
)
from trampoline_vision.contracts.tracking import BoundingBox, BoxMeasurement, TrackingCandidate, TrackingFrame
from trampoline_vision.ingestion.manifest import load_manifest
from trampoline_vision.ingestion.video import probe_video
from trampoline_vision.results.tracking import tracking_record
from trampoline_vision.tracking.config import TrackerConfig
from trampoline_vision.tracking.session import TrackingSession

# El port ByteTrack és de benchmark, fora del registre de backends de producció.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "study-03"))
from explore import ExperimentalBackend


# Les variants baixes comproven si les pèrdues són només de llindar/solapament.
# Són controls exploratoris, no una cerca de paràmetres validada en altres vídeos.
VARIANTS = {
    "ocsort_boxes": ("ocsort", TrackerConfig()),
    "byte_boxes_high": ("byte_high", TrackerConfig()),
    "byte_boxes_weak": ("byte_strict", TrackerConfig()),
    "ocsort_low": ("ocsort", TrackerConfig(confidence_threshold=.02)),
    "ocsort_iou002": ("ocsort", TrackerConfig(min_iou=.02)),
    "ocsort_low_iou002": ("ocsort", TrackerConfig(confidence_threshold=.02, min_iou=.02)),
    "ocsort_low_iou002_dir0": ("ocsort", TrackerConfig(confidence_threshold=.02, min_iou=.02, direction_weight=0)),
}


def load_boxes(path: Path, video):
    """Valida CSV, indexació zero-based, confiança, geometria i cobertura completa del vídeo d'aquest experiment."""
    by_frame = defaultdict(list)
    keys = set()
    expected = {"frame", "det_id", "x1", "y1", "x2", "y2", "conf", "class_id"}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or set(reader.fieldnames) != expected or len(reader.fieldnames) != len(expected):
            raise ValueError("Unexpected recorded box CSV header")
        for line, row in enumerate(reader, 2):
            index, det_id, class_id = int(row["frame"]), int(row["det_id"]), int(row["class_id"])
            if not 0 <= index < video.frame_count or det_id < 0 or class_id != 0 or (index, det_id) in keys:
                raise ValueError(f"Invalid or duplicate CSV identity at line {line}")
            box = BoundingBox(*(float(row[k]) for k in ("x1", "y1", "x2", "y2")))
            score = float(row["conf"])
            if not math.isfinite(score) or not 0 <= score <= 1:
                raise ValueError(f"Invalid CSV confidence at line {line}")
            if box.x_min < 0 or box.y_min < 0 or box.x_max > video.width_px or box.y_max > video.height_px:
                raise ValueError(f"CSV coordinates outside original frame at line {line}")
            keys.add((index, det_id))
            by_frame[index].append((det_id, box, score, line))
    # Sense metadades de completitud no confonem un fotograma absent amb una detecció negativa.
    if set(by_frame) != set(range(video.frame_count)):
        raise ValueError("This replay requires explicit CSV coverage of every video frame")
    return by_frame


def make_frame(context, rows, path):
    """Construeix candidats amb caixes del detector i punts absents, sense derivar cap geometria d'OpenPose."""
    absent = tuple(KeypointObservation(name, None, None, 0, False, None) for name in BODY25_NAMES)
    detections, candidates = [], []
    for det_id, box, score, line in sorted(rows):
        ref = f"{context.frame_index}:yolo:{det_id}"
        provenance = DetectionProvenance(str(path), f"csv_line:{line}", context.frame_index, det_id,
                                         "recorded_yolo_boxes_no_pose", "not_recorded")
        detections.append(PersonDetection(ref, absent, provenance))
        candidates.append(TrackingCandidate(f"{context.frame_index}:yolo_candidate:{det_id}", (ref,),
                          BoxMeasurement(box, "detector", score, "legacy_yolo_detector_confidence"),
                          ("pose_not_loaded",)))
    return TrackingFrame(FrameDetections(context, tuple(detections), "present"), tuple(candidates))


def main():
    """Processa el clip complet amb els controls seleccionats, conservant associacions i incidències de tots els actors."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--boxes", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--variants", nargs="+", choices=tuple(VARIANTS), default=list(VARIANTS)[:3])
    args = parser.parse_args()
    if args.output_dir.exists():
        raise ValueError("Output directory already exists")
    manifest = load_manifest(args.manifest)
    video = probe_video(manifest.video_path, manifest.case_id)
    by_frame = load_boxes(args.boxes, video)
    assert __version__ == "0.4.0"
    variants = {name: VARIANTS[name] for name in args.variants}
    sessions, counters, ids = {}, {}, {}
    for name, (kind, config) in variants.items():
        session = TrackingSession(config, video.fps)
        session.backend = ExperimentalBackend(session.config, video.fps, kind)
        session.backend.confirmed_ids = lambda current=session: set(current.live)
        sessions[name], counters[name], ids[name] = session, Counter(), str(uuid4())
    args.output_dir.mkdir(parents=True)
    from contextlib import ExitStack
    with ExitStack() as stack:
        streams = {name: stack.enter_context((args.output_dir / f"{name}.frames.jsonl").open("x", encoding="utf-8")) for name in variants}
        for index in range(video.frame_count):
            frame = make_frame(video.frame(index), by_frame[index], args.boxes)
            for name, session in sessions.items():
                result = session.update(frame)
                record = tracking_record(result, session.events, session.config)
                record.update({"run_id": ids[name], "experiment": name, "pose_status": "not_loaded"})
                if name.startswith("byte"):
                    for item in record["tracks"] + record["events"]:
                        item["track_id"] = item["track_id"].replace("ocsort:", "bytetrack:", 1)
                streams[name].write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
                counters[name]["observed_samples"] += sum(t.evidence == "observed" for t in result.tracks)
                counters[name]["predicted_samples"] += sum(t.state == "lost" for t in result.tracks)
                counters[name].update(e.kind for e in session.events)
            if index % 200 == 0:
                print(f"Processed {index}/{video.frame_count - 1}", flush=True)
    summary = {"software_version": __version__, "video_id": manifest.case_id,
               "video": {"path": str(video.path), "frames": video.frame_count, "width": video.width_px,
                         "height": video.height_px, "duration_s": video.duration_s},
               "csv": {"path": str(args.boxes), "sha256": hashlib.sha256(args.boxes.read_bytes()).hexdigest(),
                       "rows": sum(map(len, by_frame.values())), "frame_index_base": 0,
                       "per_frame_counts": sorted(set(map(len, by_frame.values())))},
               "variants": {name: {"kind": kind, "tracker_config": asdict(config)} for name, (kind, config) in variants.items()},
               "counters_all_actors": {name: dict(counter) for name, counter in counters.items()},
               "notes": ["det_id_is_not_track_id", "no_pose_input", "no_new_inference",
                         "historical_detector_weights_not_recorded_in_csv", "all_actors_retained"]}
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
