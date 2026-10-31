"""Una iteració explícita amb snapshots, preflight i traspàs a un agent revisor."""

import argparse
from contextlib import redirect_stderr, redirect_stdout
import json
from pathlib import Path
import sys
import traceback

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from benchmarks.calibration.engine.paths import CALIBRATION_ROOT, CONFIG_ROOT, ITERATION_ROOT
from benchmarks.calibration.engine.common import atomic_json, digest, exclusive_run, read_json, sha256, verify_artifacts
from benchmarks.calibration.reviews.tracking_report import build_review, snapshot
from benchmarks.calibration.reviews.detection_report import build_detection_review
from benchmarks.calibration.reviews.decisions import validate_decisions
from benchmarks.calibration.engine.sampling import validate_sampling
from benchmarks.calibration.engine.run import now, parser as benchmark_parser, resolve_plan, run, runtime

HERE = CALIBRATION_ROOT


class Tee:
    def __init__(self, terminal, log):
        self.terminal, self.log = terminal, log

    def write(self, value):
        self.terminal.write(value)
        self.log.write(value)
        self.log.flush()
        return len(value)

    def flush(self):
        self.terminal.flush()
        self.log.flush()


def prepare(args):
    value = read_json(args.plan)
    keys = {"schema_version", "iteration_id", "objective", "hypothesis", "experiment", "suite", "cases", "detectors",
            "trackers", "annotations", "allow_provisional_references", "overlay", "expected"}
    if set(value) - {"title", "detector_only", "review_decisions", "sampling_plan"} != keys or value["schema_version"] != "1.0":
        raise ValueError("Expected iteration schema 1.0 with documented keys and optional title/detector_only/review_decisions/sampling_plan")
    if "title" in value and (not isinstance(value["title"], str) or not value["title"].strip()):
        raise ValueError("Iteration title must be nonempty text")
    detector_only = value.get("detector_only", False)
    if type(detector_only) is not bool:
        raise ValueError("detector_only must be boolean")
    for key in ("cases", "detectors"):
        if not isinstance(value[key], list) or not value[key]:
            raise ValueError(f"Explicit nonempty {key} required")
    if not isinstance(value["trackers"], list) or (not value["trackers"] and not detector_only) or (value["trackers"] and detector_only):
        raise ValueError("Detector-only plans require no trackers; tracking plans require explicit trackers")
    for key in ("allow_provisional_references", "overlay"):
        if type(value[key]) is not bool:
            raise ValueError(f"{key} must be boolean")
    if (set(value["expected"]) != {"videos", "detector_jobs", "tracking_jobs"}
            or any(type(n) is not int or n < (0 if key == "tracking_jobs" and detector_only else 1)
                   for key, n in value["expected"].items())):
        raise ValueError("Expected job counts must be explicit integers; only detector-only tracking_jobs may be zero")
    annotations = args.annotations or (args.plan.parent / value["annotations"]).resolve()
    experiment = (args.plan.parent / value["experiment"]).resolve()
    argv = ["--corpus", str(args.corpus), "--experiment", str(experiment), "--dataset", str(args.dataset),
            "--output", str(args.output / "run"), "--device", args.device, "--threads", str(args.threads),
            "--suite", value["suite"], "--annotations", str(annotations)]
    for key, option in (("cases", "--case"), ("detectors", "--detector"), ("trackers", "--tracker")):
        for item in value[key]:
            argv.extend([option, item])
    if value["allow_provisional_references"]:
        argv.append("--allow-provisional-references")
    if value["overlay"]:
        argv.append("--overlay")
    if detector_only:
        if value["overlay"]:
            raise ValueError("Detector-only plans use sampled review images, not tracker overlays")
        argv.append("--detector-only")
    parsed = benchmark_parser().parse_args(argv)
    parsed.resume = args.resume and (parsed.output / "run.json").is_file()
    if not 1 <= args.threads <= 64:
        raise ValueError("threads must be 1–64")
    if args.output.is_relative_to(args.dataset) or args.dataset.is_relative_to(args.output):
        raise ValueError("Iteration output must be separate from the dataset")
    plan = resolve_plan(parsed)
    parsed.localization_decisions = None
    if value.get("review_decisions"):
        if not detector_only:
            raise ValueError("Localization review decisions require detector-only mode")
        parsed.localization_decisions = validate_decisions(
            read_json((args.plan.parent / value["review_decisions"]).resolve()),
            {case["case_id"]: case for case in plan["cases"]}, plan["identity"]["references"],
            {detector["id"]: detector for detector in plan["detectors"]}, plan["models"])
        plan["identity"]["localization_review"] = digest(parsed.localization_decisions)
    counts = {"videos": len(plan["cases"]), "detector_jobs": len(plan["cases"]) * len(plan["detectors"]),
              "tracking_jobs": len(plan["cases"]) * len(plan["detectors"]) * len(plan["trackers"])}
    if counts != value["expected"]:
        raise ValueError(f"Planned jobs differ from declared bounds: {counts} != {value['expected']}")
    if any(plan["references"].get(case["case_id"]) is None for case in plan["cases"]):
        raise ValueError("Every selected video needs an accepted reference; more videos require more annotations")
    parsed.sampling_plan = None
    if value.get("sampling_plan"):
        if not detector_only:
            raise ValueError("Sampling plans currently require detector-only mode")
        parsed.sampling_plan = validate_sampling(
            read_json((args.plan.parent / value["sampling_plan"]).resolve()),
            {case["case_id"]: case for case in plan["cases"]}, plan["references"])
        plan["identity"]["sampling_plan"] = digest(parsed.sampling_plan)
    return value, parsed, plan


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--plan", type=Path, default=ITERATION_ROOT / "01-threshold-robustness.json")
    cli.add_argument("--corpus", type=Path, default=CONFIG_ROOT / "corpus.json")
    cli.add_argument("--dataset", type=Path, default=HERE.parents[1] / "data/calibration-v1")
    cli.add_argument("--output", type=Path, default=HERE.parents[1] / "runs/calibration/threshold-robustness-v1")
    cli.add_argument("--annotations", type=Path)
    cli.add_argument("--device", default="cuda:0")
    cli.add_argument("--threads", type=int, default=8)
    cli.add_argument("--resume", action="store_true")
    cli.add_argument("--dry-run", action="store_true")
    cli.add_argument("--review-only", action="store_true", help="Rebuild review from frozen inputs, without models or original data")
    args = cli.parse_args(argv)
    for key in ("plan", "corpus", "dataset", "output", "annotations"):
        if getattr(args, key) is not None:
            setattr(args, key, getattr(args, key).resolve())
    state, owns_state = None, False
    try:
        if args.review_only:
            state = read_json(args.output / "iteration.json")
            with exclusive_run(args.output / ".iteration.lock"):
                verify_artifacts(args.output, state["input_checksums"])
                context = read_json(args.output / "inputs/iteration-plan.json")
                if context.get("detector_only"):
                    verify_artifacts(args.output, read_json(args.output / "review/checksums.json"))
                builder = build_detection_review if context.get("detector_only") else build_review
                result = builder(args.output / "run", args.output, args.output / "inputs/references",
                                 args.output / "inputs/corpus.json", context=context)
            print(args.output / "REVIEW.md")
            return 0 if result["technical_complete"] else 1
        value, parsed, plan = prepare(args)
        print(json.dumps({"iteration": value["iteration_id"], "title": value.get("title", value["iteration_id"]),
                          **value["expected"], "overlay": value["overlay"],
                          "detector_only": value.get("detector_only", False),
                          "detector_roles": (parsed.localization_decisions or {}).get("detector_roles", {}),
                          "reference_samples": {key: {"annotated_frames": len(ref), "visible_frames": sum(s["state"] == "visible" for s in ref.values())}
                                                for key, ref in plan["references"].items()},
                          "note": ("Annotated frames are samples; complete videos are processed. AI references accepted for this study by user; original provenance preserved."
                                   if parsed.localization_decisions and parsed.localization_decisions["reference_acceptance"] else
                                   "Annotated frames are samples; complete videos are processed. Provisional AI references remain pending human validation.")}, indent=2), flush=True)
        if args.dry_run:
            return 0
        identity = digest({"iteration": value, "benchmark": plan["identity"]})
        checkpoint = args.output / "iteration.json"
        fresh = not args.output.exists()
        if not fresh and (not args.resume or not checkpoint.is_file()):
            raise ValueError("Iteration output exists; use a new output or --resume with the same plan")
        if fresh and args.resume:
            raise ValueError("--resume requires an existing iteration")
        args.output.mkdir(parents=True, exist_ok=True)
        with exclusive_run(args.output / ".iteration.lock"):
            if fresh:
                snapshot(args.output / "inputs/iteration-plan.json", value)
                snapshot(args.output / "inputs/corpus.json", plan["corpus"])
                snapshot(args.output / "inputs/experiment.json", plan["experiment"])
                snapshot(args.output / "inputs/profiles.json", plan["identity"]["profiles"])
                if parsed.localization_decisions is not None:
                    snapshot(args.output / "inputs/localization-decisions.json", parsed.localization_decisions)
                if parsed.sampling_plan is not None:
                    snapshot(args.output / "inputs/sampling-plan.json", parsed.sampling_plan)
                for case in plan["cases"]:
                    name = case["case_id"] + ".json"
                    target = args.output / "inputs/references" / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open("xb") as stream:
                        stream.write((parsed.annotations / name).read_bytes())
                state = {"schema_version": "1.0", "identity": identity, "iteration_id": value["iteration_id"],
                         "title": value.get("title", value["iteration_id"]), "created_at": now(), "status": "starting",
                         "input_checksums": {path.relative_to(args.output).as_posix(): sha256(path)
                                             for path in (args.output / "inputs").rglob("*.json")}}
                atomic_json(checkpoint, state)
                owns_state = True
                (args.output / "REVIEW.md").write_text("# Iteració encara incompleta\n\nConsulteu iteration.json i execution.log. No hi ha cap decisió de qualitat.\n", encoding="utf-8")
            else:
                state = read_json(checkpoint)
                if state["identity"] != identity:
                    raise ValueError("Cannot resume after changing plan, references, inputs, code or configuration")
                verify_artifacts(args.output, state["input_checksums"])
                owns_state = True
            with (args.output / "execution.log").open("a", encoding="utf-8") as log, \
                    redirect_stdout(Tee(sys.stdout, log)), redirect_stderr(Tee(sys.stderr, log)):
                state.update(status="preflight", updated_at=now())
                atomic_json(checkpoint, state)
                environment = runtime(args.device, args.threads, [item["config"].backend for item in plan["trackers"]])
                atomic_json(args.output / "preflight.json", environment)
                state.update(status="running")
                atomic_json(checkpoint, state)
                code = run(parsed, plan, environment)
                state.update(status="review_pending", benchmark_exit_code=code, updated_at=now())
                atomic_json(checkpoint, state)
                if value.get("detector_only"):
                    review = build_detection_review(parsed.output, args.output, args.output / "inputs/references",
                                                    args.output / "inputs/corpus.json", context=value, dataset=parsed.dataset,
                                                    decisions=parsed.localization_decisions)
                else:
                    review = build_review(parsed.output, args.output, args.output / "inputs/references",
                                          args.output / "inputs/corpus.json", context=value)
                state.update(status="ready_for_review" if code == 0 and review["technical_complete"] else "incomplete", updated_at=now())
                atomic_json(checkpoint, state)
                print(f"Review package: {args.output / 'REVIEW.md'}", flush=True)
                return 0 if code == 0 and review["technical_complete"] else 1
    except Exception as exc:
        if owns_state and not args.review_only and (args.output / "iteration.json").is_file():
            previous = dict(state)
            try:
                with exclusive_run(args.output / ".iteration.lock"):
                    if read_json(args.output / "iteration.json") == previous:
                        state.update(status="failed", error=f"{type(exc).__name__}: {exc}", updated_at=now())
                        atomic_json(args.output / "iteration.json", state)
                        with (args.output / "execution.log").open("a", encoding="utf-8") as log:
                            log.write(traceback.format_exc())
                        (args.output / "REVIEW.md").write_text(f"# Iteració incompleta\n\n{state['error']}\n\nConsulteu iteration.json, inputs/iteration-plan.json i execution.log. No és un resultat de qualitat complet.\n", encoding="utf-8")
            except (ValueError, OSError):
                pass  # Un altre executor pot haver reprès la iteració; no sobreescriure'l.
        cli.exit(1, f"Iteration failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
