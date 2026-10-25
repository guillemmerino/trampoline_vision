"""Genera fulls de revisió del vídeo amb caixes originals i identitats observades.

El retall lateral només facilita la inspecció humana: mai entra al detector
ni al tracker. Les prediccions no es presenten com a mesures observades.
"""

import argparse
import colorsys
import hashlib
import json
from pathlib import Path
import cv2
from PIL import Image, ImageDraw


def color(tid):
    """Assigna un color estable a cada ID sense implicar identitat entre execucions."""
    hue = int(hashlib.sha256(tid.encode()).hexdigest()[:8], 16) / 0xffffffff
    return tuple(round(v * 255) for v in colorsys.hsv_to_rgb(hue, .8, 1))


def main():
    """Dibuixa els instants sol·licitats amb el seu índex original i no sobreescriu imatges."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--records', type=Path, required=True)
    parser.add_argument('--frames', nargs='+', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--track-id', help='Mostra una sola identitat sense alterar el replay original')
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Contact sheet already exists')
    wanted = set(args.frames)
    records = {}
    with args.records.open(encoding='utf-8') as stream:
        for line in stream:
            record = json.loads(line)
            if record['context']['frame_index'] in wanted:
                records[record['context']['frame_index']] = record
    capture = cv2.VideoCapture(str(args.video))
    width, height = 330, 560
    sheet = Image.new('RGB', (width * 4, height * ((len(args.frames) + 3)//4)), '#101820')
    for cell, index in enumerate(args.frames):
        capture.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = capture.read()
        if not ok:
            raise ValueError(f'Cannot decode {index}')
        image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(image)
        for track in records[index]['tracks']:
            box = track['bbox']
            if args.track_id and track['track_id'] != args.track_id:
                continue
            if track['evidence'] != 'observed' or box is None or box['x_min'] > 600:
                continue
            coords = [box[k] for k in ('x_min', 'y_min', 'x_max', 'y_max')]
            shade = color(track['track_id'])
            draw.rectangle(coords, outline=shade, width=3)
            draw.text((coords[0], max(0, coords[1]-13)), track['track_id'], fill=shade, stroke_width=1, stroke_fill='black')
        # Mateixes coordenades de vídeo: només s'amaga el panell negre lateral en aquesta làmina.
        image = image.crop((0, 0, 660, 1080)).resize((330, 540))
        x, y = (cell % 4)*width, (cell//4)*height
        sheet.paste(image, (x, y+20))
        ImageDraw.Draw(sheet).text((x+5, y+3), f'frame {index} | {index/30:.2f}s', fill='white')
    capture.release()
    sheet.save(args.output)


if __name__ == '__main__':
    main()
