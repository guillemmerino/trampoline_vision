"""Vídeos humans de revisió amb context, zoom i pauses als frames anotats.

No executa tracking ni interpola caixes. El temps de sortida inclou pauses;
el frame i temps ORIGINALS sempre són explícits. Les referències no es canvien.
"""

import argparse
from fractions import Fraction
import html
import json
from pathlib import Path
import subprocess
import sys
import tempfile

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from benchmarks.calibration.engine.paths import CONFIG_ROOT, ANNOTATIONS_ROOT
from benchmarks.calibration.engine.common import inside, read_json, sha256, verify_file
from benchmarks.calibration.engine.evaluation import load_reference


WIDTH, HEIGHT, FPS = 1280, 800, 30
CONTEXT_CROPS = {
    "JPN_AGE_1_000905_31.0": (100, 280, 560, 940),
    "JPN_AGE_2_000709_37.0": (480, 260, 880, 1000),
    "JPN_AGE_3_001351_19.0": (420, 250, 840, 940),
}
UNCERTAIN_CROPS = {
    "JPN_AGE_1_000905_31.0": (180, 620, 460, 940),
    "JPN_AGE_2_000709_37.0": (520, 700, 810, 1000),
    "JPN_AGE_3_001351_19.0": (440, 650, 780, 950),
}


def fonts():
    from PIL import ImageFont
    path = next((path for path in (Path("C:/Windows/Fonts/arial.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")) if path.exists()), None)
    return {size: ImageFont.truetype(str(path), size) if path else ImageFont.load_default(size=size) for size in (16, 18, 20, 24, 28)}


def fit(canvas, image, bounds):
    from PIL import Image
    x0, y0, x1, y1 = bounds
    factor = min((x1 - x0) / image.width, (y1 - y0) / image.height)
    resized = image.resize((round(image.width * factor), round(image.height * factor)), Image.Resampling.LANCZOS)
    canvas.paste(resized, (x0 + (x1 - x0 - resized.width) // 2, y0 + (y1 - y0 - resized.height) // 2))


def review_frame(raw, cid, index, sample, font, *, slow=False):
    from PIL import Image, ImageDraw
    canvas = Image.new("RGB", (WIDTH, HEIGHT), "#14212b")
    draw = ImageDraw.Draw(canvas)
    state = sample["state"] if sample else "context"
    color = "#ffd43b" if state == "visible" else "#ffb35c" if state in ("ambiguous", "occluded") else "#a8c2d2"
    labels = {"visible": "CAIXA PROVISIONAL · PAUSA PER REVISAR", "ambiguous": "AMBIGU · CAP CAIXA PROPOSADA",
              "occluded": "OCULT · CAP CAIXA PROPOSADA", "context": "CONTEXT · AQUEST FOTOGRAMA NO ESTÀ ANOTAT"}
    if slow and state == "context":
        labels["context"] = "CONTEXT DEL RESUM · SENSE PROPOSTA DIBUIXADA"
    draw.text((22, 12), f"AGE {cid.split('_')[2]} · {cid}", font=font[24], fill="white")
    draw.text((22, 46), f"Origen: F{index} · {index / FPS:.3f} s   |   " + labels[state], font=font[20], fill=color)
    draw.text((22, 81), "Fotograma complet", font=font[18], fill="#b9d1df")
    draw.text((636, 81), "Detall visual ampliat · el retall no és una anotació", font=font[18], fill="#b9d1df")
    annotated = raw.copy()
    if sample and sample["bbox_xyxy"] is not None:
        ImageDraw.Draw(annotated).rectangle(sample["bbox_xyxy"], outline="#ffd43b", width=4)
        x0, y0, x1, y1 = sample["bbox_xyxy"]
        crop = (max(0, x0 - 85), max(0, y0 - 75), min(raw.width, x1 + 85), min(raw.height, y1 + 75))
    else:
        crop = UNCERTAIN_CROPS[cid] if sample else CONTEXT_CROPS[cid]
    fit(canvas, annotated, (18, 110, 610, 718))
    fit(canvas, annotated.crop(crop), (636, 110, 1262, 718))
    draw.rectangle((0, 730, WIDTH, HEIGHT), fill="#213745")
    if state == "visible":
        draw.text((22, 742), "Revisa si el groc inclou mans i peus del gimnasta i si la caixa és massa ampla o estreta.", font=font[18], fill="white")
    elif state == "ambiguous":
        draw.text((22, 742), "Dubte de l'anotador: pots delimitar el gimnasta? Aquesta exclusió també necessita la teva revisió.", font=font[18], fill=color)
    elif state == "occluded":
        draw.text((22, 742), "L'anotador l'ha considerat tapat. Revisa el context i si realment es pot establir una caixa.", font=font[18], fill=color)
    elif slow:
        draw.text((22, 742), "Context abans/després del dubte. Els tres vídeos complets mostren totes les caixes de la mostra.", font=font[18], fill="white")
    else:
        draw.text((22, 742), "Les caixes només apareixen als fotogrames seleccionats. La resta del vídeo serveix de context.", font=font[18], fill="white")
    draw.text((22, 773), "Anotacions d'IA provisionals · No és tracking continu · " + ("Context a 1/3 de velocitat" if slow else "Velocitat original amb pauses de revisió"), font=font[16], fill="#bfd4df")
    return canvas


def write_video(path, images):
    import av
    container = av.open(str(path), "w", options={"movflags": "+faststart"})
    stream = container.add_stream("libx264", rate=FPS)
    stream.width, stream.height, stream.pix_fmt = WIDTH, HEIGHT, "yuv420p"
    stream.options = {"crf": "21", "preset": "veryfast"}
    count = 0
    try:
        for image, repeat in images:
            for _ in range(repeat):
                frame = av.VideoFrame.from_image(image)
                frame.pts, frame.time_base = count, Fraction(1, FPS)
                for packet in stream.encode(frame):
                    container.mux(packet)
                count += 1
        for packet in stream.encode():
            container.mux(packet)
    finally:
        container.close()
    if not count:
        raise ValueError("Empty review video")
    return count


def verify_video(path, expected):
    command = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_frames", "-show_streams",
               "-show_entries", "stream=codec_name,width,height,pix_fmt,nb_frames:frame=best_effort_timestamp_time", "-of", "json", str(path)]
    result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=120)
    if result.stderr.strip():
        raise ValueError(result.stderr)
    payload = json.loads(result.stdout)
    stream, frames = payload["streams"][0], payload["frames"]
    if (stream["codec_name"], stream["width"], stream["height"], stream["pix_fmt"], len(frames)) != ("h264", WIDTH, HEIGHT, "yuv420p", expected):
        raise ValueError("Review video codec/geometry/frame count mismatch")
    if any(abs(float(frame["best_effort_timestamp_time"]) - index / FPS) > .00001 for index, frame in enumerate(frames)):
        raise ValueError("Unexpected review presentation timeline")
    return {"codec": "h264", "pixel_format": "yuv420p", "frame_count": expected, "duration_s": expected / FPS,
            "dimensions": [WIDTH, HEIGHT], "all_timestamps_verified": True, "audio": "omitted"}


def iter_raw(video_path, expected_frames):
    import cv2
    from PIL import Image
    capture = cv2.VideoCapture(str(video_path))
    index = 0
    try:
        while True:
            ok, image = capture.read()
            if not ok:
                break
            yield index, Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
            index += 1
    finally:
        capture.release()
    if index != expected_frames:
        raise ValueError("Source frame coverage mismatch")


def uncertain_windows(samples, frame_count, padding=12):
    """Agrupa contextos propers; no implica associació d'actors ni noves etiquetes."""
    windows = []
    for index, sample in sorted(samples.items()):
        if sample["state"] not in ("ambiguous", "occluded"):
            continue
        start, stop = max(0, index - padding), min(frame_count, index + padding + 1)
        if windows and start <= windows[-1][1]:
            windows[-1][1] = max(stop, windows[-1][1])
        else:
            windows.append([start, stop])
    return windows


def render(corpus_path, selection_path, references, dataset, output, *, highlights_only=False):
    from trampoline_vision.infrastructure.artifacts import publish_exclusive
    corpus, selection = read_json(corpus_path), read_json(selection_path)
    cases = {case["case_id"]: case for case in corpus["cases"]}
    prepared = []
    for entry in selection["cases"]:
        cid = entry["case_id"]
        case = cases[cid]
        video = inside(dataset, case["path"])
        reference = inside(references, cid + ".json")
        verify_file(video, case["sha256"])
        if case["video"]["fps"] != FPS:
            raise ValueError("This review export currently supports the frozen 30 FPS sample")
        samples = load_reference(reference, case, allow_provisional=True)
        if samples is None or set(samples) != set(entry["frames"]):
            raise ValueError("Annotations differ from the selected sample")
        prepared.append((case, video, reference, samples))
    if output.exists():
        raise ValueError("Choose a new review video output directory")
    output.mkdir(parents=True)
    font, report = fonts(), {"purpose": "human_review_of_provisional_annotations", "source_annotations_modified": False,
                            "tracking_executed": False, "review_pauses_change_output_timeline": True, "videos": []}
    holds = []
    with tempfile.TemporaryDirectory(prefix="annotation-videos-", dir=output) as temporary:
        temp = Path(temporary)
        for ordinal, (case, video, reference, samples) in enumerate(prepared, 1):
            cid = case["case_id"]
            destination = output / f"{ordinal:02d}-AGE{cid.split('_')[2]}-revisio.mp4"
            events, output_index = [], 0
            def images():
                nonlocal output_index
                for index, raw in iter_raw(video, case["video"]["frame_count"]):
                    sample = samples.get(index)
                    repeat = 37 if sample else 1  # 1 frame original + 1,2 s de pausa afegida.
                    if sample:
                        events.append({"source_frame_index": index, "source_timestamp_s": index / FPS, "state": sample["state"],
                                       "review_start_s": output_index / FPS, "review_end_s": (output_index + repeat) / FPS,
                                       "bbox_xyxy": sample["bbox_xyxy"]})
                    yield review_frame(raw, cid, index, sample, font), repeat
                    output_index += repeat
            if not highlights_only:
                staged = temp / destination.name
                count = write_video(staged, images())
                expected = case["video"]["frame_count"] + len(samples) * 36
                if count != expected:
                    raise ValueError("Incorrect review pause schedule")
                validation = verify_video(staged, expected)
                publish_exclusive(staged, destination)
                report["videos"].append({"case_id": cid, "path": destination.name, "sha256": sha256(destination),
                                         "source_video_sha256": case["sha256"], "reference_sha256": sha256(reference),
                                         "validation": validation, "annotation_pauses": events})
                print(f"Created {destination.name}: {count/FPS:.1f}s, {len(samples)} annotated frames", flush=True)
            windows = uncertain_windows(samples, case["video"]["frame_count"])
            if windows:
                cache = {}
                wanted = {index for start, stop in windows for index in range(start, stop)}
                for index, raw in iter_raw(video, case["video"]["frame_count"]):
                    if index in wanted:
                        cache[index] = raw
                holds.append((cid, windows, cache, samples))
        destination = output / "00-casos-ambigus-i-ocult.mp4"
        highlight_events, highlight_index = [], 0
        def highlights():
            nonlocal highlight_index
            for cid, windows, cache, samples in holds:
                for start, stop in windows:
                    for index in range(start, stop):
                        sample = samples.get(index)
                        uncertain = sample and sample["state"] in ("ambiguous", "occluded")
                        repeat = 48 if uncertain else 3
                        if uncertain:
                            highlight_events.append({"case_id": cid, "source_frame_index": index, "state": sample["state"],
                                                     "review_start_s": highlight_index / FPS, "review_end_s": (highlight_index + repeat) / FPS})
                        yield review_frame(cache[index], cid, index, sample if uncertain else None, font, slow=True), repeat
                        highlight_index += repeat
        staged = temp / destination.name
        count = write_video(staged, highlights())
        if len(highlight_events) != 11:
            raise ValueError("Expected all 11 excluded annotation instants in highlights")
        validation = verify_video(staged, count)
        publish_exclusive(staged, destination)
        report["highlights"] = {"path": destination.name, "sha256": sha256(destination), "validation": validation, "events": highlight_events}
    links = ['<h2>Primer: els 11 fotogrames exclosos</h2><p>Deu casos ambigus i un ocult. Revisa si realment no es pot dibuixar una caixa.</p><video controls preload="metadata" src="00-casos-ambigus-i-ocult.mp4"></video>']
    for item in report["videos"]:
        links.append(f'<h2>{html.escape(item["case_id"])}</h2><p>Vídeo complet amb 24 pauses. Groc = caixa provisional. Sense caixa = context sense anotar, o exclusió indicada al títol.</p><video controls preload="metadata" src="{html.escape(item["path"])}"></video>')
    page = '<!doctype html><html lang="ca"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Validar anotacions provisionals</title><style>body{font:17px system-ui;max-width:1280px;margin:24px auto;background:#14212b;color:#f0f5f8;padding:0 16px}video{width:100%;max-width:1280px;background:#000}h1,h2{color:#ffd43b}p{line-height:1.5}</style><h1>Vídeos per validar la mostra d’anotacions</h1><p>72 fotogrames: 61 caixes proposades i 11 exclusions. No és tracking continu. El temps del vídeo incorpora pauses; la capçalera conserva el frame i temps originals. Les referències continuen provisionals.</p>' + ''.join(links) + '</html>'
    (output / "index.html").write_text(page, encoding="utf-8")
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--corpus", type=Path, default=CONFIG_ROOT / "corpus.json")
    cli.add_argument("--selection", type=Path, default=ANNOTATIONS_ROOT / "pilot-v1/selection.json")
    cli.add_argument("--references", type=Path, default=ANNOTATIONS_ROOT / "pilot-v1/references")
    cli.add_argument("--dataset", type=Path, default=Path("data/calibration-v1"))
    cli.add_argument("--output", type=Path, required=True)
    cli.add_argument("--highlights-only", action="store_true")
    args = cli.parse_args(argv)
    render(args.corpus, args.selection, args.references, args.dataset, args.output, highlights_only=args.highlights_only)


if __name__ == "__main__":
    main()
