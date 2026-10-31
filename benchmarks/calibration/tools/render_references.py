"""Valida i dibuixa anotacions provisionals al costat dels originals, sense models."""

import argparse
import html
import json
import os
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from benchmarks.calibration.engine.paths import CONFIG_ROOT, ANNOTATIONS_ROOT
from benchmarks.calibration.engine.common import inside, read_json, sha256, verify_file
from benchmarks.calibration.engine.evaluation import load_reference


def render(corpus_path, sample_root, references, output):
    from PIL import Image, ImageDraw, ImageFont
    if output.exists():
        raise ValueError("Choose a new review output directory")
    cases = {case["case_id"]: case for case in read_json(corpus_path)["cases"]}
    extraction = read_json(sample_root / "extraction.json")
    inputs = []
    for extracted in extraction["cases"]:
        cid = extracted["case_id"]
        reference_path = inside(references, cid + ".json")
        reference = read_json(reference_path)
        samples = load_reference(reference_path, cases[cid], allow_provisional=True)
        if samples is None or set(samples) != {entry["frame_index"] for entry in extracted["frames"]}:
            raise ValueError("Reference coverage differs from the raw sample")
        for entry in extracted["frames"]:
            path = inside(sample_root, entry["path"])
            verify_file(path, entry["png_sha256"])
            if samples[entry["frame_index"]].get("source_frame_png_sha256") != entry["png_sha256"]:
                raise ValueError("Reference was not made against the same raw PNG")
        inputs.append((extracted, reference, samples, reference_path))
    output.mkdir(parents=True)
    font_path = next((path for path in (Path("C:/Windows/Fonts/arial.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")) if path.exists()), None)
    font = ImageFont.truetype(str(font_path), 16) if font_path else ImageFont.load_default()
    sections, report = [], {"status": "model_provisional_human_review_pending", "references": {}, "cases": []}
    # Aquests crops són només per revisar dibuixos; les caixes sempre són originals.
    crops = {"JPN_AGE_1_000905_31.0": (100, 300, 560, 940),
             "JPN_AGE_2_000709_37.0": (480, 260, 880, 1000),
             "JPN_AGE_3_001351_19.0": (420, 250, 840, 940)}
    for extracted, reference, samples, reference_path in inputs:
        cid = extracted["case_id"]
        destination = output / cid
        destination.mkdir()
        cards, images = [], {}
        for entry in extracted["frames"]:
            index, sample = entry["frame_index"], samples[entry["frame_index"]]
            path = inside(sample_root, entry["path"])
            with Image.open(path) as raw:
                image = raw.convert("RGB")
            draw = ImageDraw.Draw(image)
            if sample["bbox_xyxy"] is not None:
                draw.rectangle(sample["bbox_xyxy"], outline="#ffd43b", width=3)
            annotated = destination / path.name
            image.save(annotated)
            images[index] = image
            raw_link = Path(os.path.relpath(path, output)).as_posix()
            proposed_link = annotated.relative_to(output).as_posix()
            label = f"F{index} · {sample['timestamp_s']:.3f} s · {sample['state']} · {sample['bbox_xyxy']}"
            cards.append(f'<article><h3>{html.escape(label)}</h3><div class="pair"><a href="{html.escape(raw_link)}"><img loading="lazy" src="{html.escape(raw_link)}" alt="Original F{index}"></a><a href="{html.escape(proposed_link)}"><img loading="lazy" src="{html.escape(proposed_link)}" alt="Proposta F{index}"></a></div><p>{html.escape(sample["notes"])}</p></article>')
        x0, y0, x1, y1 = extracted.get("review_crop_xyxy", crops.get(cid, (0, 0, cases[cid]["video"]["width_px"], cases[cid]["video"]["height_px"])))
        tw, th = x1 - x0 + 70, y1 - y0 + 70
        indices = sorted(samples)
        for page, start in enumerate(range(0, len(indices), 6)):
            sheet = Image.new("RGB", (tw * 3, th * 2), "#20252b")
            draw = ImageDraw.Draw(sheet)
            for cell, index in enumerate(indices[start:start + 6]):
                left, top = cell % 3 * tw, cell // 3 * th
                sheet.paste(images[index].crop((x0, y0, x1, y1)), (left + 50, top + 50))
                label = f"F{index} {samples[index]['state']}"
                draw.text((left + 5, top + 3), label, fill="#ffd43b", font=font)
                for value in range((x0 + 49) // 50 * 50, x1, 50):
                    draw.text((left + 38 + value - x0, top + 28), str(value), fill="#9edbff", font=font)
                for value in range((y0 + 49) // 50 * 50, y1, 50):
                    draw.text((left + 4, top + 42 + value - y0), str(value), fill="#9edbff", font=font)
            sheet.save(destination / f"qa-{page:02d}.jpg", quality=96)
        count = sum(sample["bbox_xyxy"] is not None for sample in samples.values())
        report["cases"].append({"case_id": cid, "samples": len(samples), "proposed_boxes": count, "excluded": len(samples) - count})
        report["references"][cid] = {"sha256": sha256(reference_path), "video_sha256": reference["video_sha256"]}
        sections.append(f'<section><h2>{html.escape(cid)}</h2><p>{count} caixes · {len(samples)-count} casos exclosos</p>{"".join(cards)}</section>')
    report["samples"] = sum(case["samples"] for case in report["cases"])
    report["proposed_boxes"] = sum(case["proposed_boxes"] for case in report["cases"])
    document = '<!doctype html><html lang="ca"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Mostra provisional d’anotacions</title><style>body{font:16px system-ui;margin:24px;background:#14202a;color:#f4f6f8}h1,h2{color:#ffd43b}article{margin:24px 0;padding:16px;background:#21323f;border-radius:8px}.pair{display:flex;gap:12px}.pair a{width:50%}img{width:100%;max-width:480px}p{max-width:1000px;line-height:1.5}</style><h1>Mostra provisional d’anotacions d’IA</h1><p>' + f'{report["samples"]} fotogrames originals de {len(inputs)} vídeos. ' + 'Esquerra: original. Dreta: proposta en groc. Clica una imatge per veure-la a mida completa. Els casos ambigus no tenen caixa. Revisió humana pendent; aquestes etiquetes no són ground truth independent.</p>' + "".join(sections) + '</html>'
    (output / "review.html").write_text(document, encoding="utf-8")
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=CONFIG_ROOT / "corpus.json")
    parser.add_argument("--sample-root", type=Path, required=True, help="Directory containing extraction.json and raw PNGs")
    parser.add_argument("--references", type=Path, default=ANNOTATIONS_ROOT / "pilot-v1/references")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(render(args.corpus, args.sample_root, args.references, args.output), indent=2))


if __name__ == "__main__":
    main()
