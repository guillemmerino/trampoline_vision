"""Avaluació de caixes de persona sense trackers, IDs, ReID ni prediccions."""

import csv
import html
import math
import os
from pathlib import Path
import time

from benchmarks.calibration.engine.paths import source_file
from benchmarks.calibration.engine.common import atomic_json, digest, inside, read_json, sha256, verify_artifacts, verify_file
from benchmarks.calibration.engine.evaluation import iou, load_reference
from benchmarks.calibration.reviews.decisions import apply_localization_review, validate_decisions
from benchmarks.calibration.reviews.tracking_report import csv_file, snapshot
from benchmarks.calibration.engine.sampling import grouped_coverage, validate_sampling


def evaluate_detections(path, case, samples, max_det):
    """Compta disponibilitat i saturació del cap sobre el CSV complet, no sobre IDs."""
    counts = [0] * case["video"]["frame_count"]
    selected = {index: [] for index in samples}
    previous = -1
    with Path(path).open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["frame", "det_id", "x1", "y1", "x2", "y2", "conf", "class_id"]:
            raise ValueError("Expected canonical detector CSV")
        for item in reader:
            index, ordinal = int(item["frame"]), int(item["det_id"])
            box = [float(item[key]) for key in ("x1", "y1", "x2", "y2")]
            confidence = float(item["conf"])
            if (not 0 <= index < len(counts) or index < previous or ordinal != counts[index]
                    or not all(math.isfinite(v) for v in [*box, confidence]) or not 0 <= confidence <= 1
                    or item["class_id"] != "0" or not 0 <= box[0] < box[2] <= case["video"]["width_px"]
                    or not 0 <= box[1] < box[3] <= case["video"]["height_px"]):
                raise ValueError("Invalid detector CSV row or ordering")
            previous = index
            counts[index] += 1
            if counts[index] > max_det:
                raise ValueError("More detections than declared max_det")
            if index in selected:
                selected[index].append({"det_id": ordinal, "bbox_xyxy": box, "confidence": confidence})
    results = []
    for index, reference in sorted(samples.items()):
        visible = reference["state"] == "visible"
        ranked = sorted(((iou(box["bbox_xyxy"], reference["bbox_xyxy"]), box) for box in selected[index]),
                        key=lambda pair: (-pair[0], pair[1]["det_id"])) if visible else []
        compatible = [box for overlap, box in ranked if overlap >= .5]
        best = ranked[0] if ranked else None
        results.append({"frame_index": index, "timestamp_s": index / case["video"]["fps"],
                        "reference_state": reference["state"], "detector_available": bool(compatible) if visible else None,
                        "matching_boxes": len(compatible) if visible else None,
                        "max_iou": best[0] if best else (0 if visible else None),
                        "best_iou_box_confidence": best[1]["confidence"] if best else None,
                        "max_matching_confidence": max((b["confidence"] for b in compatible), default=None),
                        "boxes_in_frame": counts[index], "at_max_det": counts[index] == max_det})
    visible_rows = [r for r in results if r["reference_state"] == "visible"]
    metrics = {"visible_samples": len(visible_rows), "excluded_samples": len(results) - len(visible_rows),
               "detector_available_samples": sum(r["detector_available"] for r in visible_rows),
               "duplicate_matching_samples": sum(r["matching_boxes"] > 1 for r in visible_rows),
               "total_boxes": sum(counts), "frame_count": len(counts), "max_boxes_in_frame": max(counts),
               "frames_at_max_det": sum(count == max_det for count in counts),
               "samples_at_max_det": sum(r["at_max_det"] for r in results),
               "missing_visible_frames": [r["frame_index"] for r in visible_rows if not r["detector_available"]],
               "iou_threshold": .5,
               "cap_note": "Reaching max_det indicates possible truncation, not proof that the gymnast was discarded."}
    return metrics, results, selected


def render_samples(dataset, cases, references, variants, output, accepted_cases=()):
    """Una làmina per frame anotat, amb totes les confiances."""
    from PIL import Image, ImageDraw, ImageFont
    from trampoline_vision.ingestion.video import probe_video
    from trampoline_vision.ingestion.video_frames import VideoFrameReader
    font = ImageFont.load_default(size=14)
    generated = []
    for case_id, case in cases.items():
        video = probe_video(inside(dataset, case["path"]), case_id)
        expected = case["video"]
        if (video.width_px, video.height_px, video.frame_count) != (expected["width_px"], expected["height_px"], expected["frame_count"]) or abs(video.duration_s - expected["duration_s"]) > .01:
            raise ValueError("Review video timeline differs from corpus")
        reader = VideoFrameReader(video)
        selected_variants = [v for v in variants if v["case_id"] == case_id]
        try:
            for index, reference in sorted(references[case_id].items()):
                original = Image.fromarray(reader.get(index).to_ndarray(format="rgb24"))
                sheet = Image.new("RGB", (360 * len(selected_variants), 450), "#111827")
                draw = ImageDraw.Draw(sheet)
                acceptance = "AI reference accepted for study" if case_id in accepted_cases else "AI reference, human review pending"
                draw.text((8, 4), f"{case_id} | f{index} | {reference['state']} | {acceptance}", font=font, fill="white")
                target = reference["bbox_xyxy"]
                for column, variant in enumerate(selected_variants):
                    image = original.copy()
                    painter = ImageDraw.Draw(image)
                    candidates = variant["boxes"][index]
                    for box in candidates:
                        painter.rectangle(box["bbox_xyxy"], outline="#9ca3af", width=1)
                    if target:
                        if candidates:
                            best = max(candidates, key=lambda box: iou(box["bbox_xyxy"], target))
                            painter.rectangle(best["bbox_xyxy"], outline="#22c55e" if iou(best["bbox_xyxy"], target) >= .5 else "#ef4444", width=3)
                        painter.rectangle(target, outline="#fde047", width=3)
                        size = min(max(360, max(target[2]-target[0], target[3]-target[1]) + 160), min(image.size))
                        left = max(0, min(image.width-size, (target[0]+target[2]-size)/2))
                        top = max(0, min(image.height-size, (target[1]+target[3]-size)/2))
                        image = image.crop((round(left), round(top), round(left+size), round(top+size)))
                    image.thumbnail((350, 350))
                    sheet.paste(image, (column*360+5, 90))
                    result = next(r for r in variant["samples"] if r["frame_index"] == index)
                    draw.text((column*360+5, 30), f"conf={variant['confidence']:g} | boxes={len(candidates)}", font=font, fill="white")
                    label = f"IoU={result['max_iou']:.3f} | matches={result['matching_boxes']}" if target else "Excluded reference; not evaluated"
                    draw.text((column*360+5, 51), label, font=font, fill="#fde047")
                    draw.text((column*360+5, 70), result["localization_class"] + " | " + result["localization_source"], font=font, fill="#93c5fd")
                destination = output / "images" / case_id / f"frame-{index:06d}.jpg"
                destination.parent.mkdir(parents=True, exist_ok=True)
                sheet.save(destination, quality=90)
                generated.append(destination)
        finally:
            reader.close()
    return generated


def build_detection_review(run_root, output, annotations, corpus_path, *, context=None, dataset=None, decisions=None):
    run_root, output = Path(run_root).resolve(), Path(output).resolve()
    record = read_json(run_root / "run.json")
    identity, signature = record["identity"], record["signature"]
    if digest(identity) != signature or not identity.get("detector_only") or identity["trackers"]:
        raise ValueError("Expected a verified detector-only run")
    corpus = read_json(corpus_path)
    if digest(corpus) != identity["corpus"]:
        raise ValueError("Review corpus differs from run")
    cases = {c["case_id"]: c for c in corpus["cases"] if c["case_id"] in identity["cases"]}
    settings = {d["id"]: d for d in identity["experiment"]["detectors"]}
    decisions_path = output / "inputs/localization-decisions.json"
    if decisions is None and decisions_path.exists():
        decisions = read_json(decisions_path)
    if decisions is not None:
        validate_decisions(decisions, cases, identity["references"], settings, {m["model_id"]: m for m in corpus["models"]})
        snapshot(decisions_path, decisions)
    decisions = decisions or {"reference_acceptance": [], "decisions": [], "detector_roles": {}}
    accepted_cases = {e["case_id"] for e in decisions["reference_acceptance"]}
    references, originals = {}, {}
    for case_id, case in cases.items():
        path = inside(annotations, case_id + ".json")
        verify_file(path, identity["references"][case_id])
        references[case_id] = load_reference(path, case, allow_provisional=identity["allow_provisional_references"])
        if references[case_id] is None:
            raise ValueError("Every case needs accepted references")
        originals[case_id] = read_json(path)
    sampling_path = output / "inputs/sampling-plan.json"
    sampling = None
    if identity.get("sampling_plan"):
        sampling = validate_sampling(read_json(sampling_path), cases, references)
        if digest(sampling) != identity["sampling_plan"]:
            raise ValueError("Frozen sampling plan differs from the run")
    sampling_cases = {entry["case_id"]: entry for entry in sampling["cases"]} if sampling else {}
    review = output / "review"
    review.mkdir(parents=True, exist_ok=True)
    if (review / "review.json").exists() and read_json(review / "review.json")["run_signature"] != signature:
        raise ValueError("Review belongs to another run")
    snapshot(output / "inputs/run.json", record)
    rows, sample_rows, variants = [], [], []
    for case_id, case in cases.items():
        for detector in identity["detectors"]:
            job = run_root / "detections" / case_id / detector
            row = {"case_id": case_id, "detector": detector, "confidence": settings[detector]["confidence"],
                   "partition": sampling_cases.get(case_id, {}).get("partition", "unspecified"),
                   "detector_role": decisions["detector_roles"].get(detector),
                   "status": "incomplete", "reference_status": originals[case_id]["status"],
                   "human_reviewed": originals[case_id].get("human_reviewed"),
                   "reference_accepted_for_study": case_id in accepted_cases,
                   "evaluation_status": None, "visible_samples": None, "excluded_samples": None,
                   "detector_available_samples": None, "duplicate_matching_samples": None,
                   "sufficient_localization_samples": None, "partial_localization_samples": None,
                   "absent_or_incorrect_samples": None, "needs_review_samples": None, "explicitly_reviewed_samples": None,
                   "total_boxes": None, "frame_count": None, "max_boxes_in_frame": None,
                   "frames_at_max_det": None, "samples_at_max_det": None, "detection_elapsed_s": None,
                   "peak_rss_bytes": None, "peak_cuda_allocated_bytes": None, "peak_cuda_reserved_bytes": None,
                   "boxes_csv": None, "error": None}
            if (job / "completed.json").exists():
                complete = read_json(job / "completed.json")
                if complete["signature"] != digest({"run": signature, "case": case_id, "detector": settings[detector]}):
                    raise ValueError("Detector completion identity differs")
                verify_artifacts(job, complete["artifacts"])
                attempt = inside(job, complete["attempt"])
                metrics, samples, boxes = evaluate_detections(attempt / "boxes.csv", case, references[case_id], settings[detector]["max_det"])
                selected_decisions = [entry for entry in decisions["decisions"] if entry["case_id"] == case_id and entry["detector"] == detector]
                metrics.update(apply_localization_review(samples, boxes, selected_decisions))
                if metrics["frame_count"] != complete["metrics"]["frame_count"] or metrics["total_boxes"] != complete["metrics"]["boxes"]:
                    raise ValueError("Detector CSV and completed report counts differ")
                resource = complete["resources"]
                row.update({key: metrics[key] for key in ("visible_samples", "excluded_samples", "detector_available_samples", "duplicate_matching_samples", "total_boxes", "frame_count", "max_boxes_in_frame", "frames_at_max_det", "samples_at_max_det")})
                row.update({key: metrics[key] for key in ("sufficient_localization_samples", "partial_localization_samples",
                                                         "absent_or_incorrect_samples", "needs_review_samples", "explicitly_reviewed_samples")})
                row.update(status="succeeded", evaluation_status="evaluated_provisional_sparse" if originals[case_id]["status"] == "provisional" else "evaluated_sparse",
                           detection_elapsed_s=resource["elapsed_s"], peak_rss_bytes=resource["peak_rss_bytes"],
                           peak_cuda_allocated_bytes=resource.get("peak_cuda_allocated_bytes"), peak_cuda_reserved_bytes=resource.get("peak_cuda_reserved_bytes"),
                           boxes_csv=Path(os.path.relpath(attempt / "boxes.csv", output)).as_posix())
                for sample in samples:
                    strata = [key.removesuffix("_frames") for key in ("uniform_frames", "legacy_frames", "dense_frames")
                              if sample["frame_index"] in sampling_cases.get(case_id, {}).get(key, [])]
                    sample_rows.append({"case_id": case_id, "detector": detector, "confidence": row["confidence"],
                                        "partition": row["partition"], "sampling_strata": strata, **sample})
                variants.append({"case_id": case_id, "detector": detector, "confidence": row["confidence"], "metrics": metrics, "samples": samples, "boxes": boxes})
            else:
                row["error"] = "No completed detector checkpoint; inspect run/events.jsonl and execution.log"
            rows.append(row)
    all_complete = all(row["status"] == "succeeded" for row in rows)
    render_s = None
    if dataset is not None and variants:
        started = time.perf_counter()
        rendered_cases = {key: case for key, case in cases.items() if any(v["case_id"] == key for v in variants)}
        render_samples(dataset, rendered_cases, references, variants, review, accepted_cases)
        render_s = time.perf_counter() - started
    elif (review / "review.json").exists():
        render_s = read_json(review / "review.json").get("sample_render_elapsed_s")
    if all_complete and not all((review / "images" / case / f"frame-{index:06d}.jpg").is_file() for case, refs in references.items() for index in refs):
        raise ValueError("Review images missing; generate them with dataset available")
    payload = {"schema_version": "1.0", "run_signature": signature, "title": context.get("title") if context else None,
               "detector_only": True, "technical_complete": all_complete, "quality_decision": "pending_independent_review",
               "context": context, "runtime": identity["runtime"], "rows": rows,
               "localization_decisions": decisions, "sampling_plan": sampling,
               "grouped_coverage": grouped_coverage(sample_rows) if sampling else [],
               "evaluations": [{key: value for key, value in v.items() if key != "boxes"} for v in variants],
               "sample_render_elapsed_s": render_s, "timing_scope": "detector load/decode/resize/predict/CSV only; review rendering measured separately; no MP4 or tracker",
               "analysis_code": {name: sha256(source_file(name)) for name in ("detection_review.py", "detection_decisions.py", "evaluation.py", "sampling.py")}}
    atomic_json(review / "review.json", payload)
    csv_file(review / "summary.csv", rows)
    if sampling:
        csv_file(review / "grouped-coverage.csv", payload["grouped_coverage"])
    if sample_rows:
        csv_file(review / "samples.csv", sample_rows)
    else:
        (review / "samples.csv").write_text("case_id,detector,frame_index\n", encoding="utf-8")
    title = payload["title"] or "Prova de detecció amb llindars baixos"
    lines = [f"# {title}", "", f"Estat tècnic: {'complet' if all_complete else 'INCOMPLET'}. Qualitat pendent de revisió.", "",
             "Objectiu: que hi hagi una caixa útil del gimnasta, encara que hi hagi soroll o duplicats. "
             "S’han processat els vídeos complets; només s’avaluen els fotogrames anotats. "
             "No s’ha executat cap tracker, ReID, predicció temporal ni recovery offline.", "",
             ("**Les bboxes d’IA s’accepten com a referència d’aquest estudi per decisió de l’usuari.** "
              "Es conserva la procedència original; això no acredita una revisió humana independent de totes les caixes. "
              if set(cases) <= accepted_cases else "**Les referències d’IA són provisionals, pendents de validació humana.** ") +
             "Una mostra és un fotograma anotat. Caixa compatible significa IoU ≥0,5; el score de YOLO no és una probabilitat calibrada. "
             "Els estats ocult/ambigu s’exclouen de la mètrica, però també són a la galeria.", "",
             "## Hipòtesi congelada", "",
             "El text següent correspon al pla d’inferència original; l’acceptació i les decisions posteriors es registren separadament sense reescriure els resultats històrics.", "",
             str((context or {}).get("hypothesis", "")), "",
             "## Resultats", "", "| Vídeo | Confiança | Rol | Estat | IoU ≥0,5 / visibles | Suficients | Parcials | Pendents | Caixes totals | Frames a max_det | CSV |",
             "| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for row in rows:
        available = f"{row['detector_available_samples']}/{row['visible_samples']}" if row["visible_samples"] is not None else "pendent"
        link = f"[CSV]({row['boxes_csv']})" if row["boxes_csv"] else "—"
        lines.append(f"| {row['case_id']} | {row['confidence']:g} | {row['detector_role'] or '—'} | {row['status']} | {available} | {row['sufficient_localization_samples']} | {row['partial_localization_samples']} | {row['needs_review_samples']} | {row['total_boxes']} | {row['frames_at_max_det']} | {link} |")
    lines += ["", "## Utilitat de les deteccions", "",
              "L’IoU i detector_available es mantenen intactes. Sufficient indica IoU ≥0,5 o acceptació explícita de la caixa revisada. "
              "Partial identifica una caixa observada parcial aprofitable per a una associació posterior, amb partial_bbox=true. "
              "Absent_or_incorrect indica absència o rebuig explícit. Needs_review és un cas sota el llindar geomètric encara sense decisió. "
              "La parcialitat no s’infereix de la confiança. Aquestes etiquetes són d’avaluació; no canvien deteccions ni comportament del tracker.", "",
              "Les decisions explícites estan vinculades al vídeo, hash de referència, model, paràmetres i coordenades/confiança exactes de la candidata. "
              "[Registre de decisions](inputs/localization-decisions.json)." if decisions_path.exists() else "No hi ha decisions explícites congelades.",
              "", "## Revisió en una conversa nova", "",
              "1. Verifica iteration.json si existeix, inputs/run.json, review/checksums.json i els completed.json abans d’interpretar els resultats.",
              "2. Compara candidat principal i control si hi ha rols declarats; altrament compara llindars sobre el mateix vídeo. Prioritza presència i qualitat de la caixa del gimnasta; "
              "no calculis continuïtat d’IDs, perquè aquí no hi ha trackers.",
              "3. Revisa a [la galeria](review/index.html) els frames sense caixa útil i els recuperats, i també les exclusions. "
              "Groc: referència provisional; verd/vermell: millor caixa segons IoU; gris: altres deteccions.",
              "4. Si s’arriba a max_det=300, registra possible truncament. No és prova que s’hagi descartat el gimnasta. "
              "Proposa un control amb cap més alt només si la saturació ho justifica.",
              "5. Entrega conclusions i la hipòtesi següent, sense canviar defaults ni iniciar altres bateries.", "",
              "[Mètriques, temps, RAM i VRAM](review/summary.csv). [Resultats per fotograma](review/samples.csv). "
              "[Configuració efectiva i runtime](inputs/run.json). "
              "El temps del detector no inclou les làmines; sample_render_elapsed_s es registra separadament. "
              "No hi ha MP4 ni ús de cache d’aparença. Les deteccions completes es conserven als CSV amb checksums.", ""]
    if sampling:
        lines += ["## Particions i mostreig", "",
                  "[Selecció congelada](inputs/sampling-plan.json). [Cobertura per partició i estrat](review/grouped-coverage.csv). "
                  "Compara desenvolupament i reserva separadament. La reserva és temporal, de la mateixa captura; "
                  "no s’ha demostrat independència d’esportistes. Un cop consultats els resultats, deixa de ser una reserva intacta. "
                  "Les àncores uniformes són el resum principal; les finestres denses i els casos antics són diagnòstics. "
                  "Els estrats poden solapar-se i no s’han de sumar. Cap proporció dispersa equival a cobertura de tots els frames.", "",
                  "| Partició | Detector | Estrat | IoU ≥0,5 / visibles | Exclosos | Suficients | Parcials | Pendents |",
                  "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |"]
        for group in payload["grouped_coverage"]:
            lines.append(f"| {group['partition']} | {group['detector']} | {group['stratum']} | "
                         f"{group['detector_available_samples']}/{group['visible_samples']} | {group['excluded_samples']} | "
                         f"{group['sufficient']} | {group['partial']} | {group['needs_review']} |")
        lines.append("")
    (output / "REVIEW.md").write_text("\n".join(lines), encoding="utf-8")
    page = [f'<!doctype html><html lang="ca"><meta charset="utf-8"><title>{html.escape(title)}</title>',
            '<style>body{font:16px system-ui;max-width:1500px;margin:auto;padding:20px}img{width:100%}section{margin:30px 0}</style>',
            f'<h1>{html.escape(title)}</h1><p>Referències d’IA; consulteu l’acceptació per a l’estudi i les decisions explícites a l’informe. '
            '<a href="../REVIEW.md">Informe</a> · <a href="samples.csv">Frames i mètriques</a></p>']
    for case_id, refs in references.items():
        for index in sorted(refs):
            path = review / "images" / case_id / f"frame-{index:06d}.jpg"
            if path.is_file():
                src = html.escape(path.relative_to(review).as_posix(), quote=True)
                assessments = [f"{r['confidence']:g}: {r['localization_class']} ({r['localization_source']})" for r in sample_rows
                               if r['case_id'] == case_id and r['frame_index'] == index]
                page.append(f'<section><h2>{html.escape(case_id)} · frame {index}</h2><p>{html.escape(" · ".join(assessments))}</p><a href="{src}"><img loading="lazy" src="{src}"></a></section>')
    (review / "index.html").write_text("\n".join(page) + "</html>\n", encoding="utf-8")
    paths = [output / "REVIEW.md", review / "review.json", review / "summary.csv", review / "samples.csv", review / "index.html",
             *(output / "inputs").rglob("*.json"), *(review / "images").rglob("*.jpg")]
    if sampling:
        paths.append(review / "grouped-coverage.csv")
    atomic_json(review / "checksums.json", {p.relative_to(output).as_posix(): sha256(p) for p in paths})
    return payload
