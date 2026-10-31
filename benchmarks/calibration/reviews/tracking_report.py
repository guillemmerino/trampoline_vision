"""Paquet de revisió independent, només a partir de traces i referències verificades."""

import argparse
import csv
import html
import os
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from benchmarks.calibration.engine.paths import CONFIG_ROOT, source_file
from benchmarks.calibration.engine.common import atomic_json, digest, inside, read_json, sha256, verify_artifacts, verify_file
from benchmarks.calibration.engine.evaluation import evaluate, load_reference


def snapshot(path, value):
    """Una còpia existent només s'accepta si és lògicament idèntica."""
    if path.exists():
        if read_json(path) != value:
            raise ValueError(f"Snapshot differs: {path}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(path, value)


def csv_file(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def build_review(run_root, output, annotations, corpus_path, *, context=None):
    """Verifica artefactes; no importa models, no uneix IDs i no declara un òptim."""
    run_root, output = Path(run_root).resolve(), Path(output).resolve()
    record = read_json(run_root / "run.json")
    identity, signature = record["identity"], record["signature"]
    if digest(identity) != signature:
        raise ValueError("Run identity/signature differs")
    corpus = read_json(corpus_path)
    if digest(corpus) != identity["corpus"]:
        raise ValueError("Review corpus differs from run")
    cases = {case["case_id"]: case for case in corpus["cases"]}
    refs, originals = {}, {}
    for case_id in identity["cases"]:
        path = inside(annotations, case_id + ".json")
        verify_file(path, identity["references"][case_id])
        refs[case_id] = load_reference(path, cases[case_id], allow_provisional=identity["allow_provisional_references"])
        if refs[case_id] is None:
            raise ValueError(f"No accepted reference for {case_id}")
        originals[case_id] = read_json(path)
    marker = output / "review" / "review.json"
    if marker.exists() and read_json(marker)["run_signature"] != signature:
        raise ValueError("Review output belongs to another run")
    output.mkdir(parents=True, exist_ok=True)
    review = output / "review"
    review.mkdir(exist_ok=True)
    snapshot(output / "inputs/run.json", record)
    snapshot(output / "inputs/corpus.json", corpus)
    snapshot(output / "inputs/experiment.json", identity["experiment"])
    snapshot(output / "inputs/profiles.json", identity["profiles"])
    for case_id in originals:
        target = output / "inputs/references" / (case_id + ".json")
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(inside(annotations, case_id + ".json").read_bytes())
        verify_file(target, identity["references"][case_id])
    rows, samples, evaluations = [], [], []
    detector_settings = {item["id"]: item for item in identity["experiment"]["detectors"]}
    for case_id in identity["cases"]:
        for detector in identity["detectors"]:
            detection_root = run_root / "detections" / case_id / detector
            detection_path = detection_root / "completed.json"
            detection = read_json(detection_path) if detection_path.exists() else None
            if detection:
                if detection["signature"] != digest({"run": signature, "case": case_id, "detector": detector_settings[detector]}):
                    raise ValueError("Detector completion belongs to another run")
                verify_artifacts(detection_root, detection["artifacts"])
            for tracker in identity["trackers"]:
                job = run_root / "tracking" / case_id / detector / tracker
                checkpoint = job / "completed.json"
                row = dict(case_id=case_id, detector=detector, tracker=tracker, status="incomplete",
                           reference_status=originals[case_id]["status"], human_reviewed=originals[case_id].get("human_reviewed"),
                           evaluation_status=None,
                           visible_samples=None, excluded_samples=None, detector_available_samples=None,
                           observed_matches=None, best_fixed_id=None, best_fixed_id_observed_matches=None,
                           seed_fixed_id_observed_matches=None, id_changes_between_matches=None,
                           prediction_only_samples=None, detector_elapsed_s=None, tracking_with_export_s=None,
                           peak_rss_bytes=None, peak_cuda_allocated_bytes=None, peak_cuda_reserved_bytes=None,
                           appearance_cache_hit_frames=None, appearance_cache_miss_frames=None,
                           observed_samples_all_actors=None, predicted_samples_all_actors=None, mp4=None, error=None)
                if checkpoint.exists():
                    result = read_json(checkpoint)
                    if not detection or result["signature"] != signature:
                        raise ValueError("Tracking completion belongs to another run or has no detector")
                    verify_artifacts(job, result["artifacts"])
                    attempt = inside(job, result["attempt"])
                    evaluation = evaluate(attempt / "frames.jsonl", refs[case_id], video_id=case_id)
                    if originals[case_id]["status"] == "provisional":
                        evaluation["status"] = "evaluated_provisional_sparse"
                        evaluation["limitations"].append("model_generated_reference_not_human_validated")
                    tracking = read_json(attempt / "tracking.json")
                    if tracking["totals"]["frames"] != cases[case_id]["video"]["frame_count"] or not tracking["validation"]["frame_sequence_verified"]:
                        raise ValueError("Review requires full-video, frame-zero tracking")
                    resource = result["resources"]
                    row.update(status="succeeded", evaluation_status=evaluation["status"], visible_samples=evaluation["visible_samples"],
                               excluded_samples=evaluation["excluded_samples"],
                               detector_available_samples=evaluation["detector_available_samples"],
                               observed_matches=evaluation["observed_matches"], best_fixed_id=evaluation["best_fixed_id"],
                               best_fixed_id_observed_matches=evaluation["best_fixed_id_observed_matches"],
                               seed_fixed_id_observed_matches=evaluation["seed_fixed_id_observed_matches"],
                               id_changes_between_matches=evaluation["id_changes_between_reviewed_matches"],
                               prediction_only_samples=evaluation["samples_with_matching_prediction_only"],
                               detector_elapsed_s=detection["resources"]["elapsed_s"], tracking_with_export_s=resource["elapsed_s"],
                               peak_rss_bytes=resource["peak_rss_bytes"], peak_cuda_allocated_bytes=resource.get("peak_cuda_allocated_bytes"),
                               peak_cuda_reserved_bytes=resource.get("peak_cuda_reserved_bytes"),
                               appearance_cache_hit_frames=result["metrics"]["appearance_cache_hit_frames"],
                               appearance_cache_miss_frames=result["metrics"]["appearance_cache_miss_frames"],
                               observed_samples_all_actors=result["metrics"]["observed_samples_all_actors"],
                               predicted_samples_all_actors=result["metrics"]["predicted_samples_all_actors"])
                    if identity["overlay"]:
                        video = attempt / "overlay.mp4"
                        if not tracking["validation"].get("frame_count_verified") or not tracking["validation"].get("timestamps_verified"):
                            raise ValueError("Overlay lacks frame/timestamp validation")
                        row["mp4"] = Path(os.path.relpath(video, output)).as_posix()
                    for sample in evaluation["samples"]:
                        samples.append({"case_id": case_id, "detector": detector, "tracker": tracker, **sample})
                    evaluations.append({"case_id": case_id, "detector": detector, "tracker": tracker,
                                        "reference": originals[case_id], "evaluation": evaluation})
                else:
                    failure = job / "last-failure.json"
                    row["error"] = read_json(failure)["error"] if failure.exists() else "No completed checkpoint"
                rows.append(row)
    complete = all(row["status"] == "succeeded" for row in rows)
    source_frames = sum(cases[case_id]["video"]["frame_count"] for case_id in identity["cases"])
    payload = {"schema_version": "1.0", "run_signature": signature, "technical_complete": complete, "source_frames": source_frames,
               "quality_decision": "pending_independent_review", "context": context,
               "overlay": identity["overlay"], "runtime": identity["runtime"], "rows": rows,
               "analysis_code": {name: sha256(source_file(name)) for name in ("review.py", "evaluation.py")}}
    csv_file(review / "summary.csv", rows)
    if samples:
        csv_file(review / "samples.csv", samples)
    else:
        (review / "samples.csv").write_text("case_id,detector,tracker,frame_index\n", encoding="utf-8")
    atomic_json(review / "evaluations.json", evaluations)
    atomic_json(review / "review.json", payload)
    n = sum(len(ref) for ref in refs.values())
    visible = sum(sample["state"] == "visible" for ref in refs.values() for sample in ref.values())
    provisional = any(value["status"] == "provisional" for value in originals.values())
    title = context.get("title", "Revisió d’una iteració de tracking") if context else "Revisió d’una iteració de tracking"
    lines = [f"# {title}", "",
             f"Estat tècnic: {'complet' if complete else 'INCOMPLET'}. Decisió de qualitat: pendent de revisió.", "",
             "## Context suficient per a una conversa nova", "",
             "Objectiu: mantenir la caixa i la identitat del gimnasta, abans de qualsevol recovery offline. "
             "Els trackers segueixen tots els actors; aquest experiment no implementa selecció automàtica del gimnasta.", "",
             f"S’han seleccionat {len(identity['cases'])} vídeos que sumen {source_frames} fotogrames originals. Una mostra és UN fotograma anotat: "
             f"{n} anotats, {visible} visibles i {n-visible} exclosos. Els vídeos es processen sencers des del frame zero.", "",
             "Les referències contenen anotacions d’IA provisionals, pendents de validació humana." if provisional else
             "Consulteu estat, revisor i procedència de les referències congelades a inputs/references/.", "",
             "Caixa compatible: IoU ≥ 0,5 amb la caixa anotada. «Qualsevol ID» pot canviar de track entre mostres. "
             "«ID fix» escull retrospectivament el millor ID per vídeo: és optimista i no acredita puresa entre mostres. "
             "Les prediccions no compten com a observacions. Les mostres escasses no mesuren tots els buits/canvis del vídeo.", ""]
    if context:
        lines += ["## Hipòtesi i abast congelats", "", str(context.get("objective", "")), "", str(context.get("hypothesis", "")), ""]
    lines += ["## Resultats per vídeo i configuració", "",
              "| Vídeo | Detector | Tracker | Estat | Detector disponible | Qualsevol ID | ID fix | Canvis entre matches | MP4 |",
              "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |"]
    for row in rows:
        denominator = row["visible_samples"]
        value = lambda key: f"{row[key]}/{denominator}" if denominator is not None else "pendent"
        video = f"[MP4]({row['mp4']})" if row["mp4"] else "—"
        lines.append(f"| {row['case_id']} | {row['detector']} | {row['tracker']} | {row['status']} | "
                     f"{value('detector_available_samples')} | {value('observed_matches')} | {value('best_fixed_id_observed_matches')} | "
                     f"{row['id_changes_between_matches']} | {video} |")
    lines += ["", "## Recursos i artefactes", "",
              "[Taula completa de temps, RAM, VRAM i cache](review/summary.csv). El detector es mesura una vegada per vídeo/variant, "
              "encara que es repeteixi a les files de cada tracker. " +
              ("Els temps de tracking inclouen generació/codificació de vídeo." if identity["overlay"] else "Aquesta iteració no codifica vídeo."), "",
              "RSS és del procés mostrejada cada 0,2 s; CUDA són pics de l’allocator PyTorch, no tota la memòria del driver/GPU. "
              "[Mostres i IDs observats/predits](review/samples.csv), [avaluacions amb procedència](review/evaluations.json), "
              "[galeria](review/index.html), [configuracions efectives i runtime](inputs/run.json).", "",
              "## Encàrrec per a l’agent revisor", "",
              "1. Comprova review/review.json, l’estat tècnic, els errors i els checksums abans de comparar qualitat.",
              "2. Llegeix inputs/iteration-plan.json si existeix, les configuracions efectives i la procedència de les referències.",
              "3. Compara variants aparellades sobre els mateixos vídeos. Separa disponibilitat del detector, cobertura amb qualsevol ID, "
              "cobertura amb ID fix, prediccions i duplicats. No escullis segons el total de fragments d’espectadors.",
              "4. Revisa als MP4 els frames de review/samples.csv sense observació, amb canvis d’ID o prediccions. "
              "Les exclusions i les anotacions d’IA també necessiten revisió humana.",
              "5. Entrega conclusions sustentades, limitacions i una hipòtesi per a la següent iteració. "
              "Prepara un nou pla si cal; no modifiquis defaults ni declaris un òptim a partir de referències provisionals.", "",
              "Prompt per a una conversa nova: «Treballa al repositori trampoline-vision. Llegeix aquest REVIEW.md i revisa "
              "els artefactes enllaçats com una iteració independent. Explica què millora, què empitjora i quin experiment faries després.»", ""]
    (output / "REVIEW.md").write_text("\n".join(lines), encoding="utf-8")
    page = ['<!doctype html><html lang="ca"><meta charset="utf-8"><title>Revisió tracking</title>',
            '<style>body{font:16px system-ui;max-width:1000px;margin:30px auto;padding:16px}video{max-height:75vh;width:100%}section{margin:35px 0}</style>',
            f'<h1>{html.escape(title)}</h1><p>Referències i qualitat: llegiu <a href="../REVIEW.md">REVIEW.md</a>. '
            'Caixa contínua: observació; discontínua: predicció. La revisió humana continua pendent quan les referències són provisionals.</p>']
    for row in rows:
        title = html.escape(f"{row['case_id']} · {row['detector']} · {row['tracker']}")
        if row["mp4"]:
            src = html.escape("../" + row["mp4"], quote=True)
            page.append(f'<section><h2>{title}</h2><video controls preload="none" src="{src}"></video></section>')
    (review / "index.html").write_text("\n".join(page) + "</html>\n", encoding="utf-8")
    paths = [output / "REVIEW.md", *review.glob("*.csv"), review / "index.html", review / "review.json", review / "evaluations.json",
             * (output / "inputs").rglob("*.json")]
    atomic_json(review / "checksums.json", {path.relative_to(output).as_posix(): sha256(path) for path in paths})
    return payload


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--run", type=Path, required=True)
    cli.add_argument("--output", type=Path, required=True, help="New directory; original run remains unchanged")
    cli.add_argument("--annotations", type=Path, required=True)
    cli.add_argument("--corpus", type=Path, default=CONFIG_ROOT / "corpus.json")
    args = cli.parse_args(argv)
    try:
        if args.output.exists() or args.output.resolve().is_relative_to(args.run.resolve()):
            raise ValueError("Choose a new review directory outside the original run")
        result = build_review(args.run, args.output, args.annotations, args.corpus)
        print(args.output.resolve() / "REVIEW.md")
        return 0 if result["technical_complete"] else 1
    except (ValueError, OSError, KeyError, TypeError) as exc:
        cli.exit(1, f"Review failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
