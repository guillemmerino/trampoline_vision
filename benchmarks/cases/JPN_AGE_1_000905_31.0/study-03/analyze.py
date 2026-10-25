"""Anàlisi pilot de geometria i identitats amb caixes visuals aproximades i àncores fixes.

No calcula HOTA/MOTA ni precisió exhaustiva. Les caixes revisades només
cobreixen dos actors en instants dispersos i poden incloure marges d'anotació.
"""

import argparse
from collections import defaultdict
import json
from pathlib import Path

from scipy.optimize import linear_sum_assignment

from trampoline_vision.application.tracking_evaluation import evaluate_tracking


VARIANTS = ("reference", "kp005", "weighted", "byte_high", "byte_weak", "byte_weighted", "byte_strict")


def read_records(path):
    """Carrega un tram curt i exigeix índexs únics; s'utilitza només per diagnòstic offline."""
    records = {}
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            index = record["context"]["frame_index"]
            if index in records:
                raise ValueError("Duplicate frame")
            records[index] = record
    return records


def iou(a, b):
    """Mesura solapament de rectangles xyxy, sense interpretar-lo com a qualitat articular."""
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
    return intersection / union if union > 0 else 0


def xyxy(box):
    """Converteix només la representació del rectangle, mantenint les coordenades originals."""
    return [box[k] for k in ("x_min", "y_min", "x_max", "y_max")]


def review_geometry(records, samples, threshold):
    """Compara disponibilitat de caixes i matches observats unívocs als instants revisats."""
    by_frame = defaultdict(list)
    for sample in samples:
        by_frame[sample["frame_index"]].append(sample)
    subjects, previous, details = {}, {}, []
    assigned_ids = defaultdict(set)
    for index in sorted(by_frame):
        annotations, record = by_frame[index], records[index]
        observed = [t for t in record["tracks"] if t["evidence"] == "observed"]
        candidates = [c for c in record["candidates"] if c["measurement"] is not None]
        matched = {}
        if observed:
            matrix = [[iou(a["bbox_xyxy"], xyxy(t["bbox"])) for t in observed] for a in annotations]
            rows, columns = linear_sum_assignment(matrix, maximize=True)
            matched = {int(r): int(c) for r, c in zip(rows, columns) if matrix[r][c] >= threshold}
        for row, annotation in enumerate(annotations):
            subject = annotation["subject_id"]
            metrics = subjects.setdefault(subject, {"samples": 0, "box_available": 0, "observed_matches": 0,
                                                     "id_changes_across_matches": 0, "track_ids": set()})
            metrics["samples"] += 1
            best = max(candidates, key=lambda c: iou(annotation["bbox_xyxy"], xyxy(c["measurement"]["bbox"])), default=None)
            best_iou = iou(annotation["bbox_xyxy"], xyxy(best["measurement"]["bbox"])) if best else 0
            metrics["box_available"] += best_iou >= threshold
            track = observed[matched[row]] if row in matched else None
            if track:
                metrics["observed_matches"] += 1
                tid = track["track_id"]
                metrics["track_ids"].add(tid)
                assigned_ids[subject].add(tid)
                if subject in previous and previous[subject] != tid:
                    metrics["id_changes_across_matches"] += 1
                previous[subject] = tid
            details.append({**annotation, "best_candidate_iou": best_iou,
                            "best_candidate_sources": best["source_detection_ids"] if best else [],
                            "track_id": track["track_id"] if track else None,
                            "track_iou": iou(annotation["bbox_xyxy"], xyxy(track["bbox"])) if track else None})
    for metrics in subjects.values():
        metrics["track_ids"] = sorted(metrics["track_ids"])
    return {"threshold": threshold, "subjects": subjects, "details": details,
            "ids_seen_on_both_subjects": sorted(assigned_ids["gymnast"] & assigned_ids["rear_spotter"])}


def main():
    """Guarda resultats nous i contrasta que el replay de referència sigui idèntic al baseline 0.4.0."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise ValueError("Analysis output already exists")
    args.output_dir.mkdir()
    boxes = json.loads((args.case_dir / "study-03/review-boxes.json").read_text())["samples"]
    results = {}
    for name in VARIANTS:
        records = {}
        anchors = {}
        for clip in ("baseline", "flight"):
            folder = "tracking-study-03-strict" if name == "byte_strict" else "tracking-study-03"
            path = args.runs / folder / f"{name}-{clip}.frames.jsonl"
            portion = read_records(path)
            records.update(portion)
            anchors[clip] = evaluate_tracking(path, args.case_dir / f"annotations-{clip}-01.json")
            (args.output_dir / f"anchors-{name}-{clip}.json").write_text(json.dumps(anchors[clip], indent=2) + "\n")
            if name == "reference":
                old = read_records(args.runs / "tracking-study-02" / f"fixed-{clip}.frames.jsonl")
                strip = lambda r: {k: v for k, v in r.items() if k not in ("run_id", "experiment")}
                assert {i: strip(r) for i, r in portion.items()} == {i: strip(r) for i, r in old.items()}, "Reference replay differs"
        results[name] = {"anchors": {clip: report["subjects"] for clip, report in anchors.items()},
                         "geometry": {str(t): review_geometry(records, boxes, t) for t in (.3, .5)}}
    output = {"reference_replay_exact": True, "variants": results,
              "limitations": ["approximate_boxes_no_independent_review", "13_gymnast_samples_and_12_spotter_samples",
                              "sparse_identity_changes_only", "geometric_overlap_is_not_anatomical_correctness"]}
    (args.output_dir / "diagnosis.json").write_text(json.dumps(output, indent=2) + "\n")
    for name, result in results.items():
        print(name, json.dumps({threshold: data["subjects"] for threshold, data in result["geometry"].items()}), flush=True)


if __name__ == "__main__":
    main()
