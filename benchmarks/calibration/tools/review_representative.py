"""Revisa visualment la preparació de producció sobre fotogrames reals, sense tracker."""

import argparse
from contextlib import closing
from dataclasses import asdict
from html import escape
import json
from pathlib import Path
import time

import cv2

from benchmarks.calibration.engine.common import sha256
from trampoline_vision.ingestion.detections import iter_recorded_frames
from trampoline_vision.ingestion.manifest import load_manifest
from trampoline_vision.ingestion.video import probe_video
from trampoline_vision.ingestion.video_frames import VideoFrameReader
from trampoline_vision.preparation.config import PreparationConfig
from trampoline_vision.preparation.foreground import sample_indices
from trampoline_vision.preparation.representative import RepresentativeBoxPreparer
from trampoline_vision.results.preparation import preparation_record


def _layer(boxes, color):
    """Dibuixa geometria original en SVG; el navegador la sobreposa als píxels sense retallar."""
    return ''.join(f'<rect x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}" '
                   f'fill="none" stroke="{color}" stroke-width="2"/>' for x0, y0, x1, y1 in boxes)


def run(manifest_path, config_path, output, *, frames=None, samples=12):
    """Desa JSONL auditable i galeria d’una mostra explícita, rebutjant sortides existents.

    El fons usa tot el clip. Les referències d’IA no intervenen en la selecció;
    aquesta eina només mostra deteccions i regions, sense calcular-ne l’exactitud.
    """
    started = time.perf_counter()
    manifest = load_manifest(Path(manifest_path))
    config_path, output = Path(config_path), Path(output)
    config = PreparationConfig.from_dict(json.loads(config_path.read_text()))
    if manifest.detections_format != 'person_boxes_csv' or config.representative_boxes is None:
        raise ValueError('Expected person boxes and a representative preparation profile')
    if output.exists():
        raise ValueError('Choose a new output directory; existing reviews are never overwritten')
    video = probe_video(manifest.video_path, manifest.case_id)
    selected = set(frames if frames is not None else sample_indices(video.frame_count, samples))
    if not selected or any(type(i) is not int or not 0 <= i < video.frame_count for i in selected):
        raise ValueError('Review frame indices must be inside the video')
    background_indices = sample_indices(video.frame_count)
    with closing(VideoFrameReader(video)) as reader:
        preparer = RepresentativeBoxPreparer(video.video_id, config,
            (reader.get(i).to_ndarray(format='bgr24') for i in background_indices))
    output.mkdir(parents=True, exist_ok=False)
    cards, totals = [], []
    with closing(VideoFrameReader(video)) as reader, (output/'frames.jsonl').open('x') as stream:
        for source in iter_recorded_frames(manifest, video, missing_frames_policy='error'):
            index = source.context.frame_index
            if index > max(selected):
                break
            if index not in selected:
                continue
            image = reader.get(index).to_ndarray(format='bgr24')
            tick = time.perf_counter()
            result = preparer.prepare_with_audit(source, image)
            elapsed = time.perf_counter() - tick
            record = preparation_record(result.frame, config, audit=result)
            record['preparation_s'] = elapsed
            stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False)+'\n')
            filename = f'frame-{index:06d}.jpg'
            if not cv2.imwrite(str(output/filename), image):
                raise OSError('Could not save review frame')
            originals = [tuple(asdict(d.bbox).values()) for d in source.detections]
            regions = [entry.bbox_xyxy for entry in result.selections]
            active = [tuple(asdict(c.measurement.bbox).values()) for c in result.frame.candidates]
            panels = ''.join(f'<figure><figcaption>{label}</figcaption><svg viewBox="0 0 {video.width_px} {video.height_px}">'
                             f'<image href="{filename}" width="{video.width_px}" height="{video.height_px}"/>'
                             f'{_layer(boxes, color)}</svg></figure>'
                             for label, boxes, color in [('Originals', originals, '#ffe05c'),
                                                       ('Regions abans del tall', regions, '#ff914d'),
                                                       ('Seleccionades', active, '#43ff8a')])
            totals.append({'frame': index, 'originals': result.source_count, 'groups': result.grouped_count,
                           'regions': result.region_count, 'selected': len(active), 'preparation_s': elapsed})
            cards.append(f'<article><h2>Frame {index}: {result.source_count} originals → {result.grouped_count} grups '
                         f'→ {result.region_count} regions → {len(active)} seleccionades</h2><div>{panels}</div>'
                         f'<details><summary>Puntuacions i decisions</summary><pre>'
                         f'{escape(json.dumps(record["selection_audit"], ensure_ascii=False, indent=2))}'
                         '</pre></details></article>')
    summary = {'case_id': video.video_id, 'config': asdict(config), 'frames': totals,
               'background_indices': background_indices, 'manifest_sha256': sha256(manifest.path),
               'config_sha256': sha256(config_path), 'detections_sha256': sha256(manifest.detections_path),
               'video_sha256': sha256(manifest.video_path),
               'code_sha256': {str(path.relative_to(Path(__file__).resolve().parents[3])): sha256(path)
                   for path in [Path(__file__).resolve(),
                       *sorted((Path(__file__).resolve().parents[3]/'src/trampoline_vision/preparation').glob('*.py')),
                       Path(__file__).resolve().parents[3]/'src/trampoline_vision/results/preparation.py']},
               'elapsed_s': time.perf_counter()-started,
               'timing_scope': 'background_decode_preparation_audit_and_jpg_export; no inference, tracker or MP4'}
    (output/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    (output/'index.html').write_text('<!doctype html><html lang="ca"><meta charset="utf-8">'
        '<title>Revisió de preparació</title><style>body{font:16px sans-serif;background:#18202a;color:white;padding:20px}'
        'article>div{display:flex}figure{margin:6px;width:33%}svg{width:100%}pre{white-space:pre-wrap}</style>'
        f'<h1>{escape(video.video_id)} — preparació sense tracking</h1>'
        '<p>Mostra de fotogrames, no avaluació exhaustiva. Groc: originals; taronja: regions; verd: seleccionades. '
        'Les puntuacions del rànquing no són confiances YOLO. Totes les fonts són a frames.jsonl.</p>'
        +''.join(cards)+'</html>')
    return summary


def main(argv=None):
    """Ofereix una revisió independent amb manifest, perfil i destinació explícits."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--frames', type=int, nargs='+')
    parser.add_argument('--samples', type=int, default=12)
    args = parser.parse_args(argv)
    run(args.manifest, args.config, args.output, frames=args.frames, samples=args.samples)
    return 0
