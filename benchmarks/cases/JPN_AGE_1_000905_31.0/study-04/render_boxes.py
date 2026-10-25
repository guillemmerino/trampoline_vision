"""Exporta replays de caixes i una trajectòria diagnòstica sense unir IDs ni omplir buits.

Reutilitza la codificació i la validació temporal del paquet. Una selecció
manual d'ID només limita el dibuix; no implementa la selecció del gimnasta.
El centre de caixa és una mesura d'imatge, no el centre de massa del cos.
"""

import argparse
from collections import Counter, deque
import csv
from dataclasses import dataclass
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from trampoline_vision.application.visualization import validate_rendered_video
from trampoline_vision.ingestion.manifest import load_manifest
from trampoline_vision.ingestion.video import probe_video
from trampoline_vision.results.overlay import HEADER_HEIGHT, RenderStyle, output_dimensions
from trampoline_vision.results.tracking import track_color
from trampoline_vision.results.video import encode_visualization
from replay_boxes import load_boxes, make_frame
from analyze_boxes import read_records, xyxy


@dataclass(frozen=True)
class RecordedOverlay:
    """Vincula registres del replay i observacions originals amb la línia temporal comuna."""

    source: object  # FrameDetections amb articulacions absents explícites.
    record: dict  # Resultat original del tracker, sense reconstruir ni alterar assignacions.

    @property
    def context(self):
        """Exposa els temps originals per contrastar-los amb cada fotograma descodificat."""
        return self.source.context

    @property
    def source_status(self):
        """Conserva la completitud del CSV de deteccions."""
        return self.source.source_status

    @property
    def detections(self):
        """Permet comptar propostes originals sense inventar coordenades articulars."""
        return self.source.detections


class ReplayRenderer:
    """Dibuixa evidència observada, prediccions i avisos manuals amb codis visuals diferents."""

    def __init__(self, track_id, ambiguous):
        """Inicialitza una cua curta de centres; no és una estimació de moviment."""
        self.track_id = track_id
        self.ambiguous = set(ambiguous)
        self.trail = deque(maxlen=45)

    def __call__(self, image, annotated, style):
        """Retorna un fotograma anotat i recomptes, sense modificar les dades del replay."""
        canvas = Image.new('RGB', output_dimensions(image.width, image.height, style), '#101820')
        canvas.paste(image.convert('RGB'), (0, HEADER_HEIGHT))
        draw, font = ImageDraw.Draw(canvas), ImageFont.load_default(size=13)
        index = annotated.context.frame_index
        tracks = [t for t in annotated.record['tracks'] if t['state'] != 'finished'
                  and (self.track_id is None or t['track_id'] == self.track_id)]
        counts = Counter(observed=0, predicted=0, ambiguous=0)
        for track in tracks:
            if track['bbox'] is None:
                continue
            observed = track['evidence'] == 'observed'
            ambiguous = self.track_id is not None and index in self.ambiguous
            label = 'AMBIGUA' if ambiguous else 'OBSERVADA' if observed else 'PREDITA'
            shade = (255, 220, 40) if ambiguous else (255, 145, 40) if not observed else track_color(track['track_id'])
            counts['observed' if observed else 'predicted'] += 1
            counts['ambiguous'] += ambiguous
            x0, y0, x1, y1 = xyxy(track['bbox'])
            if self.track_id:
                center = ((x0+x1)/2, (y0+y1)/2+HEADER_HEIGHT)
                self.trail.append((index, center, observed and not ambiguous))
            # Només es retalla el dibuix; els valors originals s'exporten intactes al CSV.
            x0, x1 = max(0, min(image.width-1, x0)), max(0, min(image.width-1, x1))
            y0, y1 = HEADER_HEIGHT+max(0, min(image.height-1, y0)), HEADER_HEIGHT+max(0, min(image.height-1, y1))
            if observed:
                draw.rectangle((x0, y0, x1, y1), outline=shade, width=3)
            else:
                for x in range(int(x0), int(x1), 10):
                    draw.line((x, y0, min(x+5, x1), y0), fill=shade, width=3)
                    draw.line((x, y1, min(x+5, x1), y1), fill=shade, width=3)
                for y in range(int(y0), int(y1), 10):
                    draw.line((x0, y, x0, min(y+5, y1)), fill=shade, width=3)
                    draw.line((x1, y, x1, min(y+5, y1)), fill=shade, width=3)
            draw.text((x0, max(HEADER_HEIGHT, y0-18)), f"{track['track_id']} {label}", font=font,
                      fill=shade, stroke_width=1, stroke_fill='black')
        # La línia només uneix dues observacions consecutives sense ambigüitat marcada.
        for a, b in zip(self.trail, list(self.trail)[1:]):
            if a[2] and b[2] and b[0] == a[0]+1:
                draw.line((*a[1], *b[1]), fill='#44ffbb', width=2)
        draw.text((8, 5), f'YOLO independent | frame {index} | t={annotated.context.timestamp_s:.3f}s | sense OpenPose', font=font, fill='white')
        detail = 'Tots els actors' if self.track_id is None else f'{self.track_id} seleccionat manualment | centre de caixa, no centre de massa'
        draw.text((8, 28), detail, font=font, fill='white')
        draw.text((8, 49), f"observades {counts['observed']} | predites {counts['predicted']} | ambigues {counts['ambiguous']}", font=font, fill='white')
        return canvas, {'tracking': dict(counts)}


def main():
    """Publica una carpeta nova amb MP4 verificat, informe i CSV de la identitat seleccionada."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--boxes', type=Path, required=True)
    parser.add_argument('--records', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--first', type=int, default=0)
    parser.add_argument('--stop', type=int)
    parser.add_argument('--track-id')
    parser.add_argument('--review', type=Path)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise ValueError('Output directory already exists')
    manifest = load_manifest(args.manifest)
    video = probe_video(manifest.video_path, manifest.case_id)
    records = read_records(args.records)
    if len(records) != video.frame_count:
        raise ValueError('Replay must cover the full video')
    for index, record in records.items():
        if record['context'] != vars(video.frame(index)):
            raise ValueError(f'Replay timeline differs at {index}')
    rows = load_boxes(args.boxes, video)
    stop = video.frame_count if args.stop is None else args.stop
    if not 0 <= args.first < stop <= video.frame_count:
        raise ValueError('Invalid output interval')
    review = json.loads(args.review.read_text(encoding='utf-8')) if args.review else {}
    if review and (review['track_id'] != args.track_id or review['range'] != [args.first, stop-1]):
        raise ValueError('Review notes do not match this identity and range')
    ambiguous = review.get('ambiguous_frames', [])
    args.output_dir.mkdir(parents=True)
    style = RenderStyle(view='all')
    annotations = (RecordedOverlay(make_frame(video.frame(i), rows[i], args.boxes).source, records[i]) for i in range(stop))
    target = args.output_dir / 'overlay.mp4'
    details = encode_visualization(video, annotations, target, style, args.first, stop,
                                   renderer=ReplayRenderer(args.track_id, ambiguous))
    rendered = probe_video(target, manifest.case_id)
    validation = validate_rendered_video(video, rendered, args.first, stop, style)
    if args.track_id:
        fields = ['frame_index', 'timestamp_s', 'track_id', 'state', 'evidence', 'candidate_id', 'candidate_score',
                  'x_min', 'y_min', 'x_max', 'y_max', 'center_x_px', 'center_y_px', 'human_review_flag']
        with (args.output_dir / 'trajectory.csv').open('x', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for index in range(args.first, stop):
                record = records[index]
                track = next((t for t in record['tracks'] if t['track_id'] == args.track_id and t['state'] != 'finished'), None)
                row = {'frame_index': index, 'timestamp_s': video.timestamps_s[index], 'track_id': args.track_id,
                       'state': track['state'] if track else 'absent', 'evidence': track['evidence'] if track else 'none',
                       'human_review_flag': 'ambiguous_box' if index in ambiguous else 'not_flagged_in_review'}
                if track:
                    row['candidate_id'] = track['candidate_id']
                    candidate = next((c for c in record['candidates'] if c['candidate_id'] == track['candidate_id']), None)
                    row['candidate_score'] = candidate['measurement']['score'] if candidate else None
                    if track['bbox']:
                        row.update(track['bbox'])
                        a, b, c, d = xyxy(track['bbox'])
                        row.update(center_x_px=(a+c)/2, center_y_px=(b+d)/2)
                writer.writerow(row)
    report = {'records': str(args.records), 'selected_track_id': args.track_id,
              'selection_method': 'manual_diagnostic' if args.track_id else 'all_tracks',
              'range': [args.first, stop-1], 'frames': rendered.frame_count, 'duration_s': rendered.duration_s,
              'review': review, 'validation': validation, 'totals': details['totals_by_view'],
              'limitations': ['box_center_is_not_center_of_mass', 'no_pose_association', 'no_identity_stitching',
                              'video_timing_validation_does_not_validate_identity', 'no_exhaustive_independent_annotations']}
    (args.output_dir / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
