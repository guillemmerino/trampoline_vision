"""Reutilitza traces del pilot 05 per provar les referències congelades; no infereix."""

import argparse
import csv
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from benchmarks.calibration.engine.paths import CALIBRATION_ROOT, CONFIG_ROOT, ANNOTATIONS_ROOT
from benchmarks.calibration.engine.common import read_json, sha256
from benchmarks.calibration.engine.evaluation import evaluate, load_reference


def compare(corpus_path, selection_path, references, runs, bindings_path, output):
    if output.exists():
        raise ValueError("Choose a new comparison output directory")
    corpus = {case["case_id"]: case for case in read_json(corpus_path)["cases"]}
    selection = read_json(selection_path)
    summary = read_json(runs / "summary.json")
    bindings = read_json(bindings_path)["cases"]
    report = {"status": "exploratory_model_reference_not_human_validated", "ranking": "not_computed",
              "source_study": "05-reid", "source_summary_sha256": sha256(runs / "summary.json"),
              "source_reference_bindings_sha256": sha256(bindings_path), "source_versions": summary["versions"],
              "new_detector_or_tracker_runs": False, "cases": {}, "pending_cases": [],
              "limitations": ["sparse_biased_sample", "model_generated_boxes_and_exclusions", "not_independent_human_ground_truth",
                              "historical_traces_not_new_server_experiment", "no_default_selected"]}
    rows = []
    for selected in selection["cases"]:
        cid = selected["case_id"]
        if cid not in summary["cases"]:
            report["pending_cases"].append({"case_id": cid, "reason": "no_previous_tracking_trace; annotate now, run at server later"})
            continue
        case, source = corpus[cid], summary["cases"][cid]
        if source["video_sha256"] != case["sha256"] or bindings[cid] != {"video_sha256": source["video_sha256"], "csv_sha256": source["csv_sha256"]}:
            raise ValueError("Historical study inputs do not match the selected frozen video")
        path = references / (cid + ".json")
        reference = read_json(path)
        if reference["status"] != "provisional" or reference.get("human_reviewed") is not False:
            raise ValueError("This pilot expects explicitly provisional model references")
        samples = load_reference(path, case, allow_provisional=True)
        variants = {}
        for variant in ("ocsort", "botsort_motion", "botsort_reid"):
            trace = runs / cid / (variant + ".frames.jsonl")
            metrics = evaluate(trace, samples, video_id=cid)
            metrics["status"] = "evaluated_provisional_sparse"
            metrics["trace_sha256"] = sha256(trace)
            variants[variant] = metrics
            rows.append({"case_id": cid, "variant": variant, "reference_status": "model_provisional", "human_reviewed": False,
                         "visible_samples": metrics["visible_samples"],
                         "excluded_samples": metrics["excluded_samples"], "detector_available_samples": metrics["detector_available_samples"],
                         "observed_matches": metrics["observed_matches"], "observed_coverage": metrics["observed_coverage"],
                         "distinct_matched_ids": metrics["distinct_matched_ids"],
                         "id_changes_between_reviewed_matches": metrics["id_changes_between_reviewed_matches"]})
        report["cases"][cid] = {"video_sha256": case["sha256"], "reference_sha256": sha256(path), "variants": variants}
    output.mkdir(parents=True)
    (output / "comparison.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if rows:
        with (output / "comparison.csv").open("x", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=CONFIG_ROOT / "corpus.json")
    parser.add_argument("--selection", type=Path, default=ANNOTATIONS_ROOT / "pilot-v1/selection.json")
    parser.add_argument("--references", type=Path, default=ANNOTATIONS_ROOT / "pilot-v1/references")
    parser.add_argument("--runs", type=Path, default=Path("runs/tracking-reid-study-05"))
    parser.add_argument("--bindings", type=Path, default=CALIBRATION_ROOT.parent / "studies/05-reid/reference-inputs.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(compare(args.corpus, args.selection, args.references, args.runs, args.bindings, args.output), indent=2))


if __name__ == "__main__":
    main()
