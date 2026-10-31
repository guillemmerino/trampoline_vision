"""Executa una bateria portable: detector → tracking existent → diagnòstic.

No ajusta automàticament paràmetres ni proclama un guanyador sense anotacions.
Cada intent conserva artefactes; --resume verifica els hashes abans de saltar-lo.
"""

import argparse
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from importlib import metadata
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from benchmarks.calibration.engine.paths import CALIBRATION_ROOT, CONFIG_ROOT, EXPERIMENT_ROOT
from benchmarks.calibration.engine.common import artifacts, atomic_json, digest, exclusive_run, inside, read_json, sha256, verify_artifacts, verify_file
from benchmarks.calibration.engine.detector import detect
from benchmarks.calibration.engine.evaluation import evaluate, load_reference

HERE = CALIBRATION_ROOT
PROJECT = HERE.parents[1]
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")


def now():
    return datetime.now(timezone.utc).isoformat()


def identifier(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError(f"Invalid portable ID: {value}")
    return value


def number(value, low, high, label, integer=False):
    if (type(value) not in ((int,) if integer else (int, float)) or not math.isfinite(value)
            or not low <= value <= high):
        raise ValueError(f"Invalid {label}: {value}")


def selected(entries, key, filters):
    ids = [identifier(entry[key]) for entry in entries]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate {key}")
    if filters and not set(filters) <= set(ids):
        raise ValueError(f"Unknown selected {key}: {sorted(set(filters) - set(ids))}")
    return [entry for entry in entries if not filters or entry[key] in filters]


def resolve_plan(args):
    import trampoline_vision
    from trampoline_vision.tracking.config import TrackerConfig
    installed = Path(trampoline_vision.__file__).resolve().parent
    source = PROJECT / "src/trampoline_vision"
    expected_code = {path.relative_to(source).as_posix(): sha256(path) for path in source.rglob("*.py")}
    actual_code = {path.relative_to(installed).as_posix(): sha256(path) for path in installed.rglob("*.py")}
    if expected_code != actual_code:
        raise ValueError("Installed package differs from checkout; rebuild the image or reinstall the current project")
    corpus = read_json(args.corpus)
    snapshot = read_json(args.dataset / "corpus.json")
    if corpus != snapshot or corpus.get("schema_version") != "1.0":
        raise ValueError("Dataset snapshot differs from the versioned corpus")
    experiment = read_json(args.experiment)
    if (set(experiment) != {"schema_version", "experiment_id", "status", "detectors", "trackers"}
            or experiment["schema_version"] != "1.0" or experiment["status"] != "experimental"):
        raise ValueError("Expected experimental calibration schema 1.0 with known keys")
    identifier(experiment["experiment_id"])
    if args.suite not in corpus["suites"]:
        raise ValueError(f"Unknown suite: {args.suite}")
    cases = selected(corpus["cases"], "case_id", corpus["suites"][args.suite])
    cases = selected(cases, "case_id", args.case)
    detectors = selected(experiment["detectors"], "id", args.detector)
    tracker_entries = selected(experiment["trackers"], "id", args.tracker)
    if not cases or not detectors or (not tracker_entries and not args.detector_only):
        raise ValueError("The selected experiment is empty")
    if args.detector_only and tracker_entries:
        raise ValueError("Detector-only experiments must declare an empty trackers list")
    models = {entry["model_id"]: entry for entry in corpus["models"]}
    required_models = set()
    for detector in detectors:
        if set(detector) != {"id", "model", "confidence", "nms_iou", "imgsz", "resize_factor", "max_det", "post_area_cap"}:
            raise ValueError("Detector has missing or unknown keys")
        if detector["model"] not in models or not detector["model"].startswith("yolov8"):
            raise ValueError("Unknown YOLO model")
        required_models.add(detector["model"])
        for key in ("confidence", "nms_iou"):
            number(detector[key], 0.000001, 1, key)
        number(detector["imgsz"], 32, 4096, "imgsz", True)
        if detector["imgsz"] % 32:
            raise ValueError("imgsz must be a multiple of 32")
        number(detector["resize_factor"], .1, 4, "resize_factor")
        number(detector["max_det"], 1, 3000, "max_det", True)
        if detector["post_area_cap"] is not None:
            number(detector["post_area_cap"], 1, detector["max_det"], "post_area_cap", True)
    trackers, profiles = [], {}
    for entry in tracker_entries:
        if set(entry) != {"id", "profile", "lifecycle", "parameters"}:
            raise ValueError("Tracker requires id, profile, lifecycle and parameters")
        path = (args.experiment.parent / entry["profile"]).resolve()
        raw = read_json(path)
        profiles[entry["id"]] = {"profile": raw, "sha256": sha256(path), "overrides": entry}
        if not isinstance(entry["lifecycle"], dict) or not isinstance(entry["parameters"], dict):
            raise ValueError("Tracker overrides must be objects")
        value = {**raw, "lifecycle": {**raw.get("lifecycle", {}), **entry["lifecycle"]},
                 "parameters": {**raw.get("parameters", {}), **entry["parameters"]}}
        if value.get("appearance") is not None:
            required_models.add("osnet")
            value["appearance"] = {"provider": "osnet", "weights": str(inside(args.dataset, models["osnet"]["path"])),
                                   "sha256": models["osnet"]["sha256"], "device": args.device,
                                   "threads": args.threads, "cache_dir": str(args.output / "appearance-cache")}
        trackers.append({"id": entry["id"], "config": TrackerConfig.from_dict(value)})
    for entry in cases + [models[key] for key in sorted(required_models)]:
        verify_file(inside(args.dataset, entry["path"]), entry["sha256"])
    refs, ref_hashes, reference_info = {}, {}, {}
    if args.annotations is not None and not args.annotations.is_dir():
        raise ValueError(f"Reference directory does not exist: {args.annotations}")
    for case in cases:
        if args.annotations:
            path = inside(args.annotations, case["case_id"] + ".json")
            if path.exists():
                refs[case["case_id"]] = load_reference(path, case, allow_provisional=args.allow_provisional_references)
                ref_hashes[case["case_id"]] = sha256(path)
                value = read_json(path)
                reference_info[case["case_id"]] = {"status": value["status"], "reviewer": value.get("reviewer"),
                                                   "human_reviewed": value.get("human_reviewed")}
    # Inclou codi no comès: la versió/commit sols no identifiquen un working tree.
    code = {path.relative_to(PROJECT).as_posix(): sha256(path)
            for root in (PROJECT / "src", HERE) for path in sorted(root.rglob("*.py"))
            if "tests" not in path.relative_to(root).parts}
    identity = {"corpus": digest(corpus), "experiment": experiment, "profiles": profiles,
                "cases": [case["case_id"] for case in cases], "detectors": [item["id"] for item in detectors],
                "trackers": [item["id"] for item in trackers], "references": ref_hashes,
                "allow_provisional_references": args.allow_provisional_references,
                "device": args.device, "threads": args.threads, "overlay": args.overlay,
                "code": code, "tracker_effective": {item["id"]: asdict(item["config"]) for item in trackers}}
    if args.detector_only:
        identity["detector_only"] = True
    return {"corpus": corpus, "experiment": experiment, "cases": cases, "detectors": detectors,
            "trackers": trackers, "models": models, "references": refs, "reference_info": reference_info, "identity": identity}


def runtime(device, threads, tracker_names):
    """Comprova capacitats abans de crear un run; no degrada CUDA a CPU."""
    for executable in ("ffprobe", "ffmpeg"):
        if not shutil.which(executable):
            raise ValueError(f"Required executable not found: {executable}")
    import cv2
    import torch
    if device.startswith("cuda"):
        index = int(device.partition(":")[2] or "0")
        if not torch.cuda.is_available() or index >= torch.cuda.device_count():
            raise ValueError(f"Requested NVIDIA device unavailable: {device}")
        torch.cuda.set_device(index)
    torch.set_num_threads(threads)
    cv2.setNumThreads(1)
    # GPU: CUDA 12.8/Blackwell. El runtime CPU històric conserva la parella anterior.
    torch_version, vision_version = ("2.7.1", "0.22.1") if device.startswith("cuda") else ("2.5.1", "0.20.1")
    expected = {"ultralytics": "8.3.116", "torch": torch_version, "torchvision": vision_version}
    if any(name in ("ocsort", "bytetrack") for name in tracker_names):
        expected["trackers"] = "2.6.1"
    if "botsort" in tracker_names:
        expected["boxmot"] = "16.0.9"
    for package, wanted in expected.items():
        if metadata.version(package).split("+")[0] != wanted:
            raise ValueError(f"Expected {package}=={wanted}; use the calibration Docker image")
    # Valida també que les extensions natives es puguin importar.
    import av
    import torchvision
    from ultralytics import YOLO
    if device.startswith("cuda"):
        # Comprova kernels reals: is_available() sol no detecta totes les incompatibilitats.
        boxes = torch.tensor([[0., 0., 1., 1.]], device=device)
        torchvision.ops.nms(boxes, torch.ones(1, device=device), .5)
        torch.cuda.synchronize(torch.device(device))
    if "botsort" in tracker_names:
        from boxmot import BotSort
    if any(name in ("ocsort", "bytetrack") for name in tracker_names):
        import trackers
    packages = {dist.metadata["Name"]: dist.version for dist in metadata.distributions() if dist.metadata["Name"]}
    gpu = None
    if device.startswith("cuda"):
        properties = torch.cuda.get_device_properties(torch.device(device))
        gpu = {"name": properties.name, "memory_bytes": properties.total_memory,
               "compute_capability": list(torch.cuda.get_device_capability(torch.device(device)))}
    driver = None
    if shutil.which("nvidia-smi"):
        driver = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
                                capture_output=True, text=True, timeout=15, check=False).stdout.strip()
    import platform
    import psutil
    return {"python": sys.version, "platform": sys.platform, "platform_release": platform.platform(),
            "cpu_logical_count": os.cpu_count(), "cpu_affinity": psutil.Process().cpu_affinity() if hasattr(psutil.Process(), "cpu_affinity") else None,
            "packages": dict(sorted(packages.items())),
            "gpu": gpu, "nvidia_smi": driver, "torch_cuda": torch.version.cuda,
            "ffmpeg": subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=15, check=True).stdout.splitlines()[0]}


@contextmanager
def monitored(device):
    """Mostreig RSS del procés i pics CUDA assignats/reservats; no memòria global del servidor."""
    import psutil
    import torch
    process, finished = psutil.Process(), threading.Event()
    baseline = process.cpu_times()
    result = {"peak_rss_bytes": process.memory_info().rss}
    if device.startswith("cuda"):
        torch.cuda.reset_peak_memory_stats(torch.device(device))
    def sample():
        while not finished.wait(.2):
            result["peak_rss_bytes"] = max(result["peak_rss_bytes"], process.memory_info().rss)
    thread = threading.Thread(target=sample, daemon=True)
    thread.start()
    started = time.perf_counter()
    try:
        yield result
    finally:
        if device.startswith("cuda"):
            torch.cuda.synchronize(torch.device(device))
            result.update(peak_cuda_allocated_bytes=torch.cuda.max_memory_allocated(torch.device(device)),
                          peak_cuda_reserved_bytes=torch.cuda.max_memory_reserved(torch.device(device)))
        result["elapsed_s"] = time.perf_counter() - started
        final = process.cpu_times()
        result["cpu_user_s"], result["cpu_system_s"] = final.user - baseline.user, final.system - baseline.system
        result["peak_rss_bytes"] = max(result["peak_rss_bytes"], process.memory_info().rss)
        finished.set()
        thread.join()


def attempt_directory(root):
    root.mkdir(parents=True, exist_ok=True)
    ordinal = 1
    while True:
        target = root / f"attempt-{ordinal:04d}"
        try:
            target.mkdir()
            return target
        except FileExistsError:
            ordinal += 1


def completed(root, signature):
    checkpoint = root / "completed.json"
    if not checkpoint.exists():
        return None
    value = read_json(checkpoint)
    if value["signature"] != signature:
        raise ValueError(f"Completed job has a different identity: {root}")
    verify_artifacts(root, value["artifacts"])
    return value


def track_summary(report, trace):
    previous, fragments = {}, 0
    with trace.open(encoding="utf-8") as stream:
        for line in stream:
            frame = json.loads(line)
            index = frame["context"]["frame_index"]
            for sample in frame["tracks"]:
                if sample["evidence"] == "observed":
                    fragments += previous.get(sample["track_id"]) != index - 1
                    previous[sample["track_id"]] = index
    tracks = report["tracks_including_warmup"]
    appearance = report.get("appearance") or {}
    return {"tracks_all_actors": len(tracks), "observed_fragments_all_actors": fragments,
            "observed_samples_all_actors": report["totals"].get("observed_track_samples", 0),
            "predicted_samples_all_actors": report["totals"].get("predicted_track_samples", 0),
            "max_unobserved_s_all_actors": max((item["max_unobserved_s"] for item in tracks), default=0),
            "appearance_extracted_candidates": appearance.get("extracted_candidates", 0),
            "appearance_cache_hit_frames": appearance.get("cache_hit_frames", 0),
            "appearance_cache_miss_frames": appearance.get("cache_miss_frames", 0)}


def export_summary(output, rows):
    import csv
    import io
    atomic_json(output / "summary.json", {"schema_version": "1.0", "updated_at": now(), "runs": rows,
                                         "ranking": "not_computed", "identity_accuracy": "requires_reviewed_references",
                                         "count_scope": "all_actors_unless_evaluation_says_target"})
    fields = ["case_id", "detector", "tracker", "status", "detection_elapsed_s", "tracking_elapsed_s",
              "detector_boxes", "tracks_all_actors", "observed_fragments_all_actors", "observed_samples_all_actors",
              "predicted_samples_all_actors", "max_unobserved_s_all_actors", "appearance_extracted_candidates",
              "appearance_cache_hit_frames", "appearance_cache_miss_frames", "peak_rss_bytes", "peak_cuda_allocated_bytes",
              "reference_status", "target_visible_samples", "target_observed_matches", "target_observed_coverage",
              "target_id_changes_between_reviewed_matches", "target_best_fixed_id", "target_best_fixed_id_observed_matches",
              "target_seed_fixed_id_observed_matches", "error"]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    # CSV és una vista regenerable del checkpoint JSON.
    from tempfile import NamedTemporaryFile
    with NamedTemporaryFile("w", encoding="utf-8", newline="", dir=output, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(buffer.getvalue())
    os.replace(temporary, output / "summary.csv")


def run(args, plan, environment):
    identity = {**plan["identity"], "runtime": environment}
    signature = digest(identity)
    checkpoint = args.output / "run.json"
    if args.output.exists():
        if not args.resume or not checkpoint.is_file():
            raise ValueError("Output already exists; choose a new directory or --resume for this run")
        if read_json(checkpoint)["signature"] != signature:
            raise ValueError("Cannot resume after changing inputs, config, references, code or runtime")
    elif args.resume:
        raise ValueError("--resume requires an existing run")
    else:
        args.output.mkdir(parents=True)
        atomic_json(checkpoint, {"schema_version": "1.0", "signature": signature, "created_at": now(),
                                 "identity": identity, "dataset": str(args.dataset)})
    with exclusive_run(args.output / ".run.lock"):
        return execute_jobs(args, plan, signature)


def execute_jobs(args, plan, signature):
    from trampoline_vision.application.tracking import track_case
    from trampoline_vision.ingestion.manifest import load_manifest
    from trampoline_vision.ingestion.video import probe_video
    from trampoline_vision.preparation.config import PreparationConfig

    rows = []
    events = args.output / "events.jsonl"
    def event(kind, **values):
        with events.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"time": now(), "kind": kind, **values}, allow_nan=False) + "\n")
        print(json.dumps({"kind": kind, **values}), flush=True)
    event("started", signature=signature)
    for case in plan["cases"]:
        video = None
        for detector in plan["detectors"]:
            detector_root = args.output / "detections" / case["case_id"] / detector["id"]
            detector_signature = digest({"run": signature, "case": case["case_id"], "detector": detector})
            try:
                detection = completed(detector_root, detector_signature)
                if video is None:
                    video = probe_video(inside(args.dataset, case["path"]), case["case_id"])
                    expected = case["video"]
                    if (video.width_px, video.height_px, video.frame_count) != (expected["width_px"], expected["height_px"], expected["frame_count"]) or abs(video.duration_s - expected["duration_s"]) > .01:
                        raise ValueError("Video timeline differs from the frozen inventory")
                if detection is None:
                    attempt = attempt_directory(detector_root)
                    event("detector_started", case_id=case["case_id"], detector=detector["id"])
                    with monitored(args.device) as resources:
                        result = detect(video, detector, inside(args.dataset, plan["models"][detector["model"]]["path"]),
                                        attempt / "boxes.csv", args.device,
                                        progress=lambda done, total: event("detector_progress", case_id=case["case_id"], detector=detector["id"], done=done, total=total))
                    manifest = {"schema_version": "1.0", "path_base": "manifest_directory", "case_id": case["case_id"],
                                "video": {"path": str(video.path), "expected": expected},
                                "detections": {"primary": {"path": "boxes.csv", "format": "person_boxes_csv", "frame_index_base": 0,
                                                           "coordinate_space": "original_frame_pixels", "frame_coverage": "complete_video",
                                                           "variant": detector["id"]}},
                                "known_issues": ["experimental_detector", "no_automatic_gymnast_selection"]}
                    atomic_json(attempt / "case.json", manifest)
                    atomic_json(attempt / "detector.json", {**result, "resources": resources,
                                                            "video_sha256": case["sha256"],
                                                            "weights_sha256": plan["models"][detector["model"]]["sha256"]})
                    detection = {"signature": detector_signature, "attempt": attempt.name, "metrics": result, "resources": resources,
                                 "artifacts": artifacts(detector_root, [attempt / "boxes.csv", attempt / "case.json", attempt / "detector.json"])}
                    atomic_json(detector_root / "completed.json", detection)
                    event("detector_finished", case_id=case["case_id"], detector=detector["id"], seconds=resources["elapsed_s"])
                else:
                    event("detector_reused", case_id=case["case_id"], detector=detector["id"])
                manifest = load_manifest(inside(detector_root, detection["attempt"] + "/case.json"))
            except Exception as exc:
                if args.detector_only:
                    rows.append({"case_id": case["case_id"], "detector": detector["id"], "tracker": None,
                                 "status": "detector_failed", "error": f"{type(exc).__name__}: {exc}"})
                for tracker in plan["trackers"]:
                    rows.append({"case_id": case["case_id"], "detector": detector["id"], "tracker": tracker["id"],
                                 "status": "detector_failed", "error": f"{type(exc).__name__}: {exc}"})
                event("detector_failed", case_id=case["case_id"], detector=detector["id"], error=str(exc))
                export_summary(args.output, rows)
                continue
            if args.detector_only:
                rows.append({"case_id": case["case_id"], "detector": detector["id"], "tracker": None,
                             "status": "succeeded", "detection_elapsed_s": detection["resources"]["elapsed_s"],
                             "detector_boxes": detection["metrics"]["boxes"], **detection["resources"]})
                export_summary(args.output, rows)
                continue
            for tracker in plan["trackers"]:
                job = args.output / "tracking" / case["case_id"] / detector["id"] / tracker["id"]
                row = {"case_id": case["case_id"], "detector": detector["id"], "tracker": tracker["id"],
                       "detection_elapsed_s": detection["resources"]["elapsed_s"], "detector_boxes": detection["metrics"]["boxes"]}
                try:
                    result = completed(job, signature)
                    if result is None:
                        attempt = attempt_directory(job)
                        event("tracking_started", **{key: row[key] for key in ("case_id", "detector", "tracker")})
                        with monitored(args.device) as resources:
                            report = track_case(manifest, video, attempt / "tracking.json", attempt / "frames.jsonl",
                                                preparation=PreparationConfig(), tracker=tracker["config"], missing_frames_policy="error",
                                                video_output=attempt / "overlay.mp4" if args.overlay else None,
                                                progress=lambda done, total: event("tracking_progress", case_id=case["case_id"], detector=detector["id"], tracker=tracker["id"], done=done, total=total) if done % 100 == 0 or done == total else None)
                        reference = plan["references"].get(case["case_id"])
                        evaluation = evaluate(attempt / "frames.jsonl", reference, video_id=case["case_id"]) if reference else {"status": "not_evaluated", "reason": "no_reviewed_reference"}
                        information = plan["reference_info"].get(case["case_id"])
                        if reference and information:
                            evaluation["reference"] = information
                            if information["status"] == "provisional":
                                evaluation["status"] = "evaluated_provisional_sparse"
                                evaluation["limitations"].append("model_generated_reference_not_human_validated")
                        atomic_json(attempt / "evaluation.json", evaluation)
                        metrics = track_summary(report, attempt / "frames.jsonl")
                        paths = [attempt / "tracking.json", attempt / "frames.jsonl", attempt / "evaluation.json"]
                        if args.overlay:
                            paths.append(attempt / "overlay.mp4")
                        result = {"signature": signature, "attempt": attempt.name, "metrics": metrics,
                                  "evaluation": evaluation, "resources": resources, "artifacts": artifacts(job, paths)}
                        atomic_json(job / "completed.json", result)
                    evaluation = result["evaluation"]
                    row.update(status="succeeded", **result["metrics"], tracking_elapsed_s=result["resources"]["elapsed_s"],
                               peak_rss_bytes=result["resources"]["peak_rss_bytes"],
                               peak_cuda_allocated_bytes=result["resources"].get("peak_cuda_allocated_bytes"),
                               reference_status=evaluation["status"], target_visible_samples=evaluation.get("visible_samples"),
                               target_observed_matches=evaluation.get("observed_matches"), target_observed_coverage=evaluation.get("observed_coverage"),
                               target_id_changes_between_reviewed_matches=evaluation.get("id_changes_between_reviewed_matches"),
                               target_best_fixed_id=evaluation.get("best_fixed_id"),
                               target_best_fixed_id_observed_matches=evaluation.get("best_fixed_id_observed_matches"),
                               target_seed_fixed_id_observed_matches=evaluation.get("seed_fixed_id_observed_matches"))
                    event("tracking_finished", case_id=case["case_id"], detector=detector["id"], tracker=tracker["id"])
                except Exception as exc:
                    row.update(status="failed", error=f"{type(exc).__name__}: {exc}")
                    atomic_json(job / "last-failure.json", {"time": now(), "error": row["error"]})
                    event("tracking_failed", case_id=case["case_id"], detector=detector["id"], tracker=tracker["id"], error=row["error"])
                rows.append(row)
                export_summary(args.output, rows)
    failures = sum(row["status"] != "succeeded" for row in rows)
    event("finished", jobs=len(rows), failures=failures)
    return 1 if failures else 0


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--corpus", type=Path, default=CONFIG_ROOT / "corpus.json")
    result.add_argument("--experiment", type=Path, default=EXPERIMENT_ROOT / "baseline.json")
    result.add_argument("--dataset", type=Path, default=PROJECT / "data/calibration-v1")
    result.add_argument("--output", type=Path, default=PROJECT / "runs/calibration-screen-v1")
    result.add_argument("--suite", default="pilot", help="smoke (3), pilot (18), all (94)")
    result.add_argument("--case", action="append", help="Restrict to an ID in the selected suite; repeatable")
    result.add_argument("--detector", action="append", help="Restrict to detector ID; repeatable")
    result.add_argument("--tracker", action="append", help="Restrict to tracker ID; repeatable")
    result.add_argument("--device", default="cuda:0")
    result.add_argument("--threads", type=int, default=8)
    result.add_argument("--annotations", type=Path, help="Optional reviewed original-video bbox references")
    result.add_argument("--allow-provisional-references", action="store_true",
                        help="Opt in to exploratory model-generated references; results remain explicitly provisional")
    result.add_argument("--overlay", action="store_true", help="Include encoding in tracking timings; expensive")
    result.add_argument("--detector-only", action="store_true", help="Run an experiment with no trackers, exporting detections only")
    result.add_argument("--resume", action="store_true")
    result.add_argument("--dry-run", action="store_true", help="Verify selected assets/configs and print plan without importing models")
    result.add_argument("--check", action="store_true", help="Also validate runtime/CUDA, without running inference")
    return result


def main(argv=None):
    cli = parser()
    args = cli.parse_args(argv)
    try:
        number(args.threads, 1, 64, "threads", True)
        if not re.fullmatch(r"cpu|cuda(?::[0-9]+)?", args.device):
            raise ValueError("Device must be cpu, cuda or cuda:N")
        if args.detector_only and args.overlay:
            raise ValueError("Detector-only mode uses annotated-frame review images, not tracker overlays")
        for name in ("corpus", "experiment", "dataset", "output", "annotations"):
            if getattr(args, name) is not None:
                setattr(args, name, getattr(args, name).resolve())
        if args.output.is_relative_to(args.dataset) or args.dataset.is_relative_to(args.output):
            raise ValueError("Outputs must be separate from the dataset")
        # Variables d'execució, no llindars ocults. Pesos sempre locals.
        os.environ["YOLO_AUTOINSTALL"] = "false"
        os.environ["YOLO_OFFLINE"] = "true"
        plan = resolve_plan(args)
        print(json.dumps({"experiment": plan["experiment"]["experiment_id"], "suite": args.suite,
                          "videos": len(plan["cases"]), "detector_jobs": len(plan["cases"]) * len(plan["detectors"]),
                          "tracking_jobs": len(plan["cases"]) * len(plan["detectors"]) * len(plan["trackers"]),
                          "source_video_seconds": sum(case["video"]["duration_s"] for case in plan["cases"]),
                          "device": args.device, "threads": args.threads, "identity_accuracy": "requires_reviewed_references"}, indent=2), flush=True)
        if args.dry_run:
            return 0
        environment = runtime(args.device, args.threads, [item["config"].backend for item in plan["trackers"]])
        if args.check:
            print(json.dumps(environment, indent=2))
            return 0
        return run(args, plan, environment)
    except (ValueError, OSError, KeyError, TypeError, RuntimeError, metadata.PackageNotFoundError, ImportError) as exc:
        cli.exit(1, f"Calibration failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
