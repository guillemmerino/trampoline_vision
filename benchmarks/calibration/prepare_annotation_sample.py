"""Extreu originals i làmines amb regles, sense consultar detectors ni trackers."""

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmarks.calibration.common import inside, read_json, sha256, verify_file


def prepare(corpus_path, selection_path, dataset, output):
    import cv2
    from PIL import Image, ImageDraw, ImageFont
    corpus, selection = read_json(corpus_path), read_json(selection_path)
    cases = {case["case_id"]: case for case in corpus["cases"]}
    if output.exists():
        raise ValueError("Choose a new sample output directory")
    # La selecció i tots els hashes es comproven abans de crear sortides.
    for entry in selection["cases"]:
        case = cases[entry["case_id"]]
        verify_file(inside(dataset, case["path"]), case["sha256"])
        indices = entry["frames"]
        if sorted(set(indices)) != indices or any(type(i) is not int or not 0 <= i < case["video"]["frame_count"] for i in indices):
            raise ValueError("Sample indices must be unique, sorted and inside the video")
        x0, y0, x1, y1 = entry["review_crop_xyxy"]
        if not 0 <= x0 < x1 <= case["video"]["width_px"] or not 0 <= y0 < y1 <= case["video"]["height_px"]:
            raise ValueError("Review crop is outside original image")
    output.mkdir(parents=True)
    font_path = next((path for path in (Path("C:/Windows/Fonts/arial.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")) if path.exists()), None)
    font = ImageFont.truetype(str(font_path), 16) if font_path else ImageFont.load_default()
    manifest = {"selection_sha256": sha256(selection_path), "corpus_id": corpus["corpus_id"],
                "inputs_shown": "raw_video_frames_only; rulers outside the image; no detections or tracker outputs", "cases": []}
    for entry in selection["cases"]:
        case, indices = cases[entry["case_id"]], entry["frames"]
        destination = output / case["case_id"]
        destination.mkdir()
        capture = cv2.VideoCapture(str(inside(dataset, case["path"])))
        wanted, frames, index = set(indices), {}, 0
        try:
            # Lectura seqüencial: no depèn de seek a keyframes ni de coordenades de models.
            while True:
                ok, array = capture.read()
                if not ok:
                    break
                if index in wanted:
                    frames[index] = Image.fromarray(cv2.cvtColor(array, cv2.COLOR_BGR2RGB))
                index += 1
        finally:
            capture.release()
        if index != case["video"]["frame_count"] or set(frames) != wanted:
            raise ValueError("Decoded sample coverage differs from frozen corpus")
        records = []
        for index in indices:
            path = destination / f"frame-{index:06d}.png"
            frames[index].save(path)
            records.append({"frame_index": index, "timestamp_s_nominal": index / case["video"]["fps"],
                            "path": path.relative_to(output).as_posix(), "png_sha256": sha256(path)})
        x0, y0, x1, y1 = entry["review_crop_xyxy"]
        width, height = x1 - x0, y1 - y0
        tile_width, tile_height = width + 70, height + 70
        for page, offset in enumerate(range(0, len(indices), 6)):
            page_indices = indices[offset:offset + 6]
            sheet = Image.new("RGB", (tile_width * 3, tile_height * 2), "#20252b")
            draw = ImageDraw.Draw(sheet)
            for cell, index in enumerate(page_indices):
                left, top = cell % 3 * tile_width, cell // 3 * tile_height
                sheet.paste(frames[index].crop((x0, y0, x1, y1)), (left + 50, top + 50))
                draw.text((left + 5, top + 3), f"F{index} | {index / case['video']['fps']:.3f}s", fill="white", font=font)
                for value in range((x0 + 49) // 50 * 50, x1, 50):
                    x = left + 50 + value - x0
                    draw.text((x - 12, top + 28), str(value), fill="#9edbff", font=font)
                    draw.line((x, top + 44, x, top + 49), fill="white")
                for value in range((y0 + 49) // 50 * 50, y1, 50):
                    y = top + 50 + value - y0
                    draw.text((left + 4, y - 8), str(value), fill="#9edbff", font=font)
                    draw.line((left + 43, y, left + 49, y), fill="white")
            sheet.save(destination / f"raw-review-{page:02d}.jpg", quality=96)
        manifest["cases"].append({"case_id": case["case_id"], "video_sha256": case["sha256"], "frames": records})
        print(case["case_id"], len(indices), "raw frames", flush=True)
    (output / "extraction.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path(__file__).with_name("corpus.json"))
    parser.add_argument("--selection", type=Path, default=Path(__file__).parent / "annotation-pilot/selection.json")
    parser.add_argument("--dataset", type=Path, default=Path("data/calibration-v1"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    prepare(args.corpus, args.selection, args.dataset, args.output)


if __name__ == "__main__":
    main()
