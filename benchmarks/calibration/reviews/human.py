"""Human review of saved detector outputs: prepare HTML, persist decisions and reassess offline."""

import argparse
import copy
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import shutil
import sys
import threading
from urllib.parse import urlsplit

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from benchmarks.calibration.engine.paths import PROJECT_ROOT, STATIC_ROOT
from benchmarks.calibration.engine.common import atomic_json, digest, exclusive_run, inside, read_json, sha256, verify_artifacts, verify_file
from benchmarks.calibration.reviews.detection_report import evaluate_detections
from benchmarks.calibration.engine.evaluation import iou, load_reference

HERE = STATIC_ROOT
DEFAULT_RUN = PROJECT_ROOT / "runs/calibration/expanded-localization-v1"
DEFAULT_RAW = PROJECT_ROOT / "runs/calibration/sample-expansion-preparation-v1/raw"


def now():
    return datetime.now(timezone.utc).isoformat()


def empty_state(bundle):
    return dict(schema_version="1.0", run_signature=bundle["run_signature"], bundle_sha256=digest(bundle),
                revision=0, reviewer="usuari", updated_at=None, entries={})


def valid_bbox(box, width, height):
    return (isinstance(box, list) and len(box) == 4 and all(type(x) in (int, float) and math.isfinite(x) for x in box)
            and 0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height)


def validate_state(state, bundle, bundle_hash=None):
    required = {"schema_version", "run_signature", "bundle_sha256", "revision", "reviewer", "updated_at", "entries"}
    if (not isinstance(state, dict) or set(state) != required or state["schema_version"] != "1.0"
            or state["run_signature"] != bundle["run_signature"] or state["bundle_sha256"] != (bundle_hash or digest(bundle))
            or type(state["revision"]) is not int or state["revision"] < 0
            or not isinstance(state["reviewer"], str) or not state["reviewer"].strip()
            or len(state["reviewer"]) > 200 or not isinstance(state["entries"], dict)
            or state["updated_at"] is not None and not isinstance(state["updated_at"], str)):
        raise ValueError("Decisions schema or frozen inputs differ")
    frames = {f["key"]: f for f in bundle["frames"]}
    for key, entry in state["entries"].items():
        if key not in frames or not isinstance(entry, dict) or set(entry) != {"presence", "reference", "detectors", "notes", "updated_at"}:
            raise ValueError("Unknown frame or review fields")
        frame = frames[key]
        if (entry["presence"] not in {"pending", "visible", "absent", "uncertain"}
                or not isinstance(entry["notes"], str) or len(entry["notes"]) > 10000
                or not isinstance(entry["updated_at"], str) or not isinstance(entry["detectors"], dict)):
            raise ValueError("Invalid frame review")
        ref = entry["reference"]
        if (not isinstance(ref, dict) or set(ref) != {"verdict", "bbox_xyxy", "source", "candidate"}
                or ref["verdict"] not in {"pending", "approved", "rejected", "missing", "corrected", "uncertain"}
                or ref["source"] not in {"original", "manual", "detector", "none"}):
            raise ValueError("Invalid reference review")
        box = ref["bbox_xyxy"]
        if box is not None and not valid_bbox(box, frame["width"], frame["height"]):
            raise ValueError("Invalid original-pixel reference bbox")
        if ref["verdict"] == "approved" and (box != frame["reference"]["bbox_xyxy"] or box is None or ref["source"] != "original"):
            raise ValueError("Approve requires the unchanged original reference bbox")
        if ref["verdict"] == "corrected" and (box is None or ref["source"] not in {"manual", "detector"}):
            raise ValueError("Correction requires an explicit drawn or selected bbox")
        if ref["verdict"] not in {"approved", "corrected"} and (box is not None or ref["source"] != "none"):
            raise ValueError("Unaccepted reference must not silently supply geometry")
        if ref["source"] == "detector":
            pointer = ref["candidate"]
            if not isinstance(pointer, dict) or set(pointer) != {"detector", "det_id"}:
                raise ValueError("Detector-assisted reference requires its exact candidate")
            matches = [c for c in frame["variants"].get(pointer["detector"], {}).get("boxes", []) if c["det_id"] == pointer["det_id"]]
            if type(pointer["det_id"]) is not int or len(matches) != 1 or matches[0]["bbox_xyxy"] != box:
                raise ValueError("Reference candidate changed or missing")
        elif ref["candidate"] is not None:
            raise ValueError("Unexpected reference candidate")
        if entry["presence"] != "visible" and ref["verdict"] in {"approved", "corrected"}:
            raise ValueError("An accepted bbox requires explicit visible gymnast")
        if set(entry["detectors"]) - set(frame["variants"]):
            raise ValueError("Unknown detector")
        for detector, decision in entry["detectors"].items():
            if (not isinstance(decision, dict) or set(decision) != {"verdict", "candidate_id"}
                    or decision["verdict"] not in {"pending", "sufficient", "partial", "incorrect", "absent"}):
                raise ValueError("Invalid detector verdict")
            candidate = decision["candidate_id"]
            if candidate is not None and (type(candidate) is not int or candidate not in {c["det_id"] for c in frame["variants"][detector]["boxes"]}):
                raise ValueError("Reviewed candidate changed or missing")
            if decision["verdict"] in {"sufficient", "partial", "incorrect"} and candidate is None:
                raise ValueError("Select the candidate being judged")
            if decision["verdict"] in {"pending", "absent"} and candidate is not None:
                raise ValueError("No candidate expected for pending/absent verdict")
            if entry["presence"] != "visible" and decision["verdict"] in {"sufficient", "partial"}:
                raise ValueError("Useful gymnast detection requires explicit visible presence")
    return state


def prepare(run_root, raw_root, output):
    run_root, raw_root, output = run_root.resolve(), raw_root.resolve(), output.resolve()
    if output.exists():
        raise ValueError("Choose a new review directory; existing human decisions are never overwritten")
    state = read_json(run_root / "iteration.json")
    verify_artifacts(run_root, state["input_checksums"])
    verify_artifacts(run_root, read_json(run_root / "review/checksums.json"))
    run = read_json(run_root / "inputs/run.json")
    identity = run["identity"]
    if digest(identity) != run["signature"] or not identity["detector_only"] or identity["trackers"]:
        raise ValueError("Expected a verified detector-only run")
    review = read_json(run_root / "review/review.json")
    if not review["technical_complete"] or review["run_signature"] != run["signature"]:
        raise ValueError("Detector run is not complete")
    cases = {c["case_id"]: c for c in read_json(run_root / "inputs/corpus.json")["cases"] if c["case_id"] in identity["cases"]}
    settings = {d["id"]: d for d in identity["experiment"]["detectors"]}
    extraction = read_json(raw_root / "extraction.json")
    raw = {(c["case_id"], f["frame_index"]): f for c in extraction["cases"] for f in c["frames"]}
    sample_plan = read_json(run_root / "inputs/sampling-plan.json")
    partitions = {e["case_id"]: e["partition"] for e in sample_plan["cases"]}
    frames = []
    # Build in memory and verify every source before publishing any files.
    sources = []
    for cid, case in cases.items():
        ref_path = run_root / "inputs/references" / (cid + ".json")
        verify_file(ref_path, identity["references"][cid])
        refs = load_reference(ref_path, case, allow_provisional=True)
        variants = {}
        for det_id in identity["detectors"]:
            job = run_root / "run/detections" / cid / det_id
            done = read_json(job / "completed.json")
            if done["signature"] != digest({"run": run["signature"], "case": cid, "detector": settings[det_id]}):
                raise ValueError("Detector checkpoint differs")
            verify_artifacts(job, done["artifacts"])
            _, samples, boxes = evaluate_detections(inside(job, done["attempt"]) / "boxes.csv", case, refs, settings[det_id]["max_det"])
            evaluated = next(e for e in review["evaluations"] if e["case_id"] == cid and e["detector"] == det_id)
            variants[det_id] = (boxes, {s["frame_index"]: s for s in evaluated["samples"]})
        for index, ref in sorted(refs.items()):
            source = raw[(cid, index)]
            if source["png_sha256"] != ref["source_frame_png_sha256"]:
                raise ValueError("Raw frame differs from reference source")
            path = inside(raw_root, source["path"])
            verify_file(path, source["png_sha256"])
            sources.append((path, Path("images") / cid / path.name))
            v = {det: dict(boxes=boxes[index], evaluation=samples[index]) for det, (boxes, samples) in variants.items()}
            a, b = [v[d]["evaluation"] for d in identity["detectors"]]
            frames.append(dict(key=f"{cid}:{index}", case_id=cid, frame_index=index, timestamp_s=index/case["video"]["fps"],
                width=case["video"]["width_px"], height=case["video"]["height_px"], partition=partitions[cid],
                video_sha256=case["sha256"], reference_sha256=identity["references"][cid], image_sha256=source["png_sha256"],
                image=(Path("images")/cid/path.name).as_posix(), reference=ref, variants=v,
                priority=(ref["state"] != "visible" or not a["detector_available"] or not b["detector_available"]),
                gain=bool(a["detector_available"] and not b["detector_available"])))
    bundle = dict(schema_version="1.0", run_signature=run["signature"], title=review["title"], detectors=settings,
                  roles=review["localization_decisions"]["detector_roles"], frames=frames)
    output.mkdir(parents=True)
    for src, relative in sources:
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)
    atomic_json(output / "bundle.json", bundle)
    initial = empty_state(bundle)
    atomic_json(output / "review-state.json", initial)
    for name in ("human_review.js", "human_review.css"):
        shutil.copyfile(HERE / name, output / name)
    document = (HERE / "human_review.html").read_text(encoding="utf-8")
    embedded = json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    document = document.replace("__BUNDLE__", embedded).replace("__STATE__", json.dumps(initial, ensure_ascii=False))
    (output / "index.html").write_text(document, encoding="utf-8")
    atomic_json(output / "checksums.json", {p.relative_to(output).as_posix(): sha256(p) for p in output.rglob("*")
                                           if p.is_file() and p.name not in {"review-state.json", "checksums.json"}})
    print(f"Prepared {len(frames)} frames: {output / 'index.html'}", flush=True)
    return bundle


def save_state(root, bundle, submitted, base_revision, bundle_hash=None):
    bundle_hash = bundle_hash or digest(bundle)
    validate_state(submitted, bundle, bundle_hash)
    if type(base_revision) is not int:
        raise ValueError("Expected base revision")
    with exclusive_run(root / ".review.lock"):
        current = validate_state(read_json(root / "review-state.json"), bundle, bundle_hash)
        if current["revision"] != base_revision:
            raise FileExistsError("Una altra pestanya ha canviat les decisions. Exporta la còpia local i recarrega abans de continuar.")
        saved = copy.deepcopy(submitted)
        saved.update(revision=current["revision"] + 1, updated_at=now())
        changes = {k: v for k, v in saved["entries"].items() if current["entries"].get(k) != v}
        event = dict(revision=saved["revision"], reviewer=saved["reviewer"], updated_at=saved["updated_at"],
                     previous_sha256=digest(current), next_sha256=digest(saved), changed_entries=changes,
                     removed_entries=sorted(set(current["entries"]) - set(saved["entries"])))
        history = root / "history"
        history.mkdir(exist_ok=True)
        path = history / f"{saved['revision']:06d}.json"
        if path.exists():
            raise ValueError("Un canvi anterior no s’ha acabat de publicar; conserva la còpia local i revisa history/ abans de continuar")
        atomic_json(path, event)
        atomic_json(root / "review-state.json", saved)
    return saved


class ReviewHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, root, bundle, **kwargs):
        self.root, self.bundle = root, bundle
        super().__init__(*args, directory=str(root), **kwargs)

    def reply(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/state":
            return self.reply(validate_state(read_json(self.root / "review-state.json"), self.bundle, self.server.bundle_hash))
        # Serve only the review interface and exact indexed images, never arbitrary files.
        allowed = {"/", "/index.html", "/human_review.js", "/human_review.css"}
        if path not in allowed and path not in self.server.image_paths:
            return self.send_error(404)
        return super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def do_POST(self):
        if self.path != "/api/state":
            return self.send_error(404)
        origin = self.headers.get("Origin")
        if (origin and urlsplit(origin).netloc != self.headers.get("Host")
                or self.headers.get("Content-Type", "").split(";")[0] != "application/json"):
            return self.reply({"error": "Només s’accepten canvis des de la pàgina de revisió"}, 403)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4_000_000:
                raise ValueError("Invalid request size")
            data = json.loads(self.rfile.read(length))
            with self.server.write_lock:
                saved = save_state(self.root, self.bundle, data["state"], data["base_revision"], self.server.bundle_hash)
            self.reply(saved)
        except FileExistsError as exc:
            self.reply({"error": str(exc)}, 409)
        except (ValueError, KeyError, TypeError) as exc:
            self.reply({"error": str(exc)}, 400)


def make_server(root, port):
    root = root.resolve()
    bundle = read_json(root / "bundle.json")
    validate_state(read_json(root / "review-state.json"), bundle)
    verify_artifacts(root, read_json(root / "checksums.json"))
    server = ThreadingHTTPServer(("127.0.0.1", port), partial(ReviewHandler, root=root, bundle=bundle))
    server.image_paths = {"/" + f["image"] for f in bundle["frames"]}
    server.bundle_hash = digest(bundle)
    server.write_lock = threading.Lock()
    return server


def reassess(root, decisions, output):
    bundle = read_json(root / "bundle.json")
    verify_artifacts(root, read_json(root / "checksums.json"))
    state = validate_state(read_json(decisions), bundle)
    if output.exists():
        raise ValueError("Choose a new assessment output; original results are preserved")
    rows, totals = [], {}
    for frame in bundle["frames"]:
        entry = state["entries"].get(frame["key"])
        reference = frame["reference"]
        box = reference["bbox_xyxy"] if reference["state"] == "visible" else None
        presence = "visible" if reference["state"] == "visible" else "uncertain"
        source = "original_ai"
        if entry:
            verdict = entry["reference"]["verdict"]
            if entry["presence"] != "pending":
                presence = entry["presence"]
            if verdict in {"approved", "corrected"}:
                box = entry["reference"]["bbox_xyxy"]
                source = "human_approved_ai" if verdict == "approved" else "human_" + entry["reference"]["source"]
            elif verdict in {"rejected", "missing", "uncertain"}:
                box = None
                source = "human_unresolved_geometry"
            if presence in {"absent", "uncertain"}:
                box = None
            if presence == "visible" and box is None:
                source = "human_visible_without_bbox"
        changed = box != reference["bbox_xyxy"] or (box is not None) != (reference["state"] == "visible")
        for detector, variant in frame["variants"].items():
            boxes = variant["boxes"]
            overlaps = [iou(c["bbox_xyxy"], box) for c in boxes] if box else []
            geometric = max(overlaps, default=0) >= .5 if box else None
            explicit = entry["detectors"].get(detector) if entry else None
            human = explicit and explicit["verdict"] != "pending"
            old = variant["evaluation"]
            utility = "sufficient" if geometric else "needs_review" if geometric is not None else "excluded"
            if not changed and old["localization_source"] == "explicit_review":
                utility = old["localization_class"]
            if human:
                # Rejecting one candidate says nothing about all other candidates.
                utility = {"incorrect": "needs_review", "absent": "absent_or_incorrect"}.get(explicit["verdict"], explicit["verdict"])
            if entry and entry["presence"] in {"absent", "uncertain"}:
                utility = "excluded"
            group = totals.setdefault(detector, dict(geometric_visible=0, geometric_available=0, excluded_geometry=0,
                human_visible=0, human_sufficient=0, human_partial=0, human_absent_or_incorrect=0, human_pending=0,
                human_rejected_candidates=0,
                corrected_references=0, sufficient=0, partial=0, absent_or_incorrect=0, needs_review=0, excluded=0))
            group["geometric_visible" if box else "excluded_geometry"] += 1
            group["geometric_available"] += bool(geometric)
            group["corrected_references"] += source in {"human_manual", "human_detector"}
            group[utility] += 1
            if entry and entry["presence"] == "visible":
                group["human_visible"] += 1
                group["human_" + utility if human and utility != "needs_review" else "human_pending"] += 1
                group["human_rejected_candidates"] += bool(human and explicit["verdict"] == "incorrect")
            rows.append(dict(case_id=frame["case_id"], frame_index=frame["frame_index"], detector=detector,
                original_available=old["detector_available"], revised_available=geometric, revised_bbox_xyxy=box,
                presence=presence, reference_source=source, human_verdict=explicit["verdict"] if explicit else "pending",
                candidate_id=explicit["candidate_id"] if explicit else None, utility=utility,
                notes=entry["notes"] if entry else ""))
    output.mkdir(parents=True)
    atomic_json(output / "decisions.json", state)
    atomic_json(output / "result.json", dict(schema_version="1.0", run_signature=bundle["run_signature"],
        bundle_sha256=digest(bundle), reviewed_entries=len(state["entries"]), totals=totals, samples=rows,
        provenance="Only explicit saved human decisions are human-reviewed. Untouched AI references remain provisional. Detector-assisted corrected boxes are human-selected YOLO outputs, not independent detector ground truth."))
    import csv
    with (output / "samples.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    lines = ["# Valoració amb decisions humanes", "", f"Fotogrames amb alguna decisió: {len(state['entries'])}/{len(bundle['frames'])}.", "",
        "Les anotacions i els resultats originals es conserven. Les caixes corregides a partir de YOLO tenen procedència detector-assisted; no són referències independents del detector.", "",
        "La cobertura geomètrica usa les caixes originals pendents i les aprovades/corregides; exclou rebutjades sense correcció, absències i geometria desconeguda. La utilitat humana es publica separadament i pot incloure gimnastes visibles sense caixa anotada.", "",
        "Rebutjar una candidata no implica rebutjar les altres del mateix frame. Només «Cap caixa útil» compta com a absència de localització útil; una candidata rebutjada queda pendent de valorar-ne una altra.", "",
        "| Detector | Geomètrica | Visibles en frames revisats | YOLO suficient per decisió humana | Parcial | Cap útil | Pendent | Candidates rebutjades |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for detector, t in totals.items():
        lines.append(f"| {detector} | {t['geometric_available']}/{t['geometric_visible']} | {t['human_visible']} | {t['human_sufficient']} | {t['human_partial']} | {t['human_absent_or_incorrect']} | {t['human_pending']} | {t['human_rejected_candidates']} |")
    (output / "ASSESSMENT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(output / "ASSESSMENT.md")
    return totals


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("prepare")
    build.add_argument("--run-root", type=Path, default=DEFAULT_RUN)
    build.add_argument("--raw-root", type=Path, default=DEFAULT_RAW)
    build.add_argument("--output", type=Path)
    serve = commands.add_parser("serve")
    serve.add_argument("--root", type=Path, default=DEFAULT_RUN / "human-review")
    serve.add_argument("--port", type=int, default=8766)
    assess = commands.add_parser("assess")
    assess.add_argument("--root", type=Path, default=DEFAULT_RUN / "human-review")
    assess.add_argument("--decisions", type=Path)
    assess.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        prepare(args.run_root, args.raw_root, args.output or args.run_root / "human-review")
    elif args.command == "serve":
        with make_server(args.root, args.port) as server:
            print(f"Revisió: http://127.0.0.1:{server.server_port}/ — desat: {args.root / 'review-state.json'}", flush=True)
            server.serve_forever()
    else:
        reassess(args.root, args.decisions or args.root / "review-state.json", args.output)


if __name__ == "__main__":
    main()
