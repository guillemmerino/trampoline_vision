"""Genera evidència visual de finestres del reconciliador amb traces congelades."""

import argparse
from collections import defaultdict
from contextlib import ExitStack, closing
import gzip
import json
from pathlib import Path

import cv2
import numpy as np

from benchmarks.calibration.engine.common import artifacts, atomic_json, inside, read_json, sha256, verify_file
from trampoline_vision.ingestion.video import probe_video
from trampoline_vision.ingestion.video_frames import VideoFrameReader

ROOT = Path(__file__).resolve().parents[3]
VARIANT = 'velocity_soft_yolo'
COLORS = ((120,235,255),(80,220,110),(230,160,65),(235,160,235),(65,170,255))


def read_assignments(run, source):
    """Verifica la traça i carrega les assignacions originals per fotograma."""
    name = 'real-traces.jsonl.gz'
    verify_file(run/name, source['assignments_sha256'])
    if source['variant'] != VARIANT:
        raise ValueError('Variant incompatible amb el catàleg')
    grouped = defaultdict(list)
    with gzip.open(run/name,'rt',encoding='utf-8') as stream:
        for row in map(json.loads,stream):
            if row['variant']==VARIANT and row['case_id'] in source['cases']:
                rows = grouped[row['case_id']]
                if row['frame_index']!=len(rows) or len(set(row['observed'].values()))!=len(row['observed']):
                    raise ValueError('Assignacions originals inconsistents')
                rows.append(row)
    return grouped


def panel(image, candidates, ids, crop, index, focus, show_candidates):
    """Mostra l’original, els IDs observats i, si escau, les candidates preparades."""
    x0,y0,x1,y1 = crop
    original = cv2.resize(image[y0:y1,x0:x1],(300,340))
    overlay = original.copy()
    prepared = original.copy()
    labels = []
    candidate_labels = []
    for candidate in candidates:
        identity = ids.get(candidate['candidate_id'])
        box = candidate['measurement']['bbox']
        left,right = [round((box[k]-x0)*300/(x1-x0)) for k in ('x_min','x_max')]
        top,bottom = [round((box[k]-y0)*340/(y1-y0)) for k in ('y_min','y_max')]
        if right<0 or left>=300 or bottom<0 or top>=340:
            continue
        x, y = max(0,min(272,left)), max(15,min(333,top-2))
        if show_candidates:
            shade = (175,210,125) if identity is not None else (235,130,235)
            cv2.rectangle(prepared,(left,top),(right,bottom),shade,1)
            candidate_labels.append((candidate['candidate_id'].rsplit(':',1)[-1],x,y,shade))
        if identity is None:
            continue
        color = COLORS[identity%len(COLORS)] if not focus or identity in focus else (125,125,125)
        cv2.rectangle(overlay,(left,top),(right,bottom),color,2 if identity in focus else 1)
        labels.append((str(identity),x,y,color))
    for layer, layer_labels in ((overlay, labels), (prepared, candidate_labels)):
        for label,x,y,color in layer_labels:
            cv2.putText(layer,label,(x,y),cv2.FONT_HERSHEY_SIMPLEX,.48,(0,0,0),3,cv2.LINE_AA)
            cv2.putText(layer,label,(x,y),cv2.FONT_HERSHEY_SIMPLEX,.48,color,1,cv2.LINE_AA)
    views = (original, overlay, prepared) if show_candidates else (original, overlay)
    header = np.full((25,300*len(views),3),25,np.uint8)
    cv2.putText(header,f'#{index} | original',(6,17),cv2.FONT_HERSHEY_SIMPLEX,.47,(240,240,240),1)
    cv2.putText(header,'velocity_soft_yolo | IDs observats',(306,17),cv2.FONT_HERSHEY_SIMPLEX,.47,(240,240,240),1)
    if show_candidates:
        cv2.putText(header,'Candidates | rosa: sense assignar',(606,17),cv2.FONT_HERSHEY_SIMPLEX,.47,(240,240,240),1)
    joined = np.vstack((header,np.hstack(views)))
    return cv2.copyMakeBorder(joined,0,1,0,0,cv2.BORDER_CONSTANT,value=(22,22,22))


def render_case(case, windows, assignments, corpus, provenance, args, evidence):
    """Comprova el vídeo i la traça de candidates, i genera les finestres sol·licitades."""
    video_path = inside(args.dataset,corpus[case]['path'])
    video_sha = provenance['video_sha256']
    verify_file(video_path,video_sha)
    video = probe_video(video_path,case)
    name = f'{case}/botsort.frames.jsonl'
    verify_file(args.source/name,provenance['candidates_sha256'])
    if video.frame_count!=len(assignments):
        raise ValueError('La traça i el vídeo tenen longituds diferents')
    previous_stop = 0
    for window in sorted(windows, key=lambda item: item['start']):
        start, stop = window['start'], window['stop']
        if not previous_stop <= start < stop <= video.frame_count:
            raise ValueError('Finestra fora de vídeo o solapada')
        previous_stop = stop
        if not window['samples'] or any(not start <= index < stop for index in window['samples']):
            raise ValueError('Mostra fora de finestra')
        for anchor in window['anchors']:
            index = anchor['frame']
            if index not in window['samples']:
                raise ValueError('Àncora absent de la làmina')
            observed = assignments[index]['observed']
            if anchor['track_id'] is not None and observed.get(anchor['candidate_id']) != anchor['track_id']:
                raise ValueError('Àncora incompatible amb la traça congelada')
    panels = defaultdict(list)
    samples = {w['id']:set(w['samples']) for w in windows}
    with ExitStack() as stack:
        reader = stack.enter_context(closing(VideoFrameReader(video)))
        source_stream = stack.enter_context((args.source/name).open(encoding='utf-8'))
        writers = {}
        if args.clips:
            for window in windows:
                path = args.output/(window['id']+'.mp4')
                width = 900 if args.show_candidates else 600
                writer = cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'mp4v'),video.fps,(width,366))
                stack.callback(writer.release)
                if not writer.isOpened():
                    raise ValueError(f'No es pot escriure {path}')
                writers[window['id']] = writer
        for index,trace in enumerate(map(json.loads,source_stream)):
            if index>=len(assignments) or trace['context']['frame_index']!=index:
                raise ValueError('Fotogrames de candidates fora d’ordre')
            selected = [w for w in windows if w['start']<=index<w['stop']]
            if not selected:
                continue
            assignment = assignments[index]
            ids = assignment['observed']
            candidates = trace['candidates']
            if not ids.keys()<={c['candidate_id'] for c in candidates}:
                raise ValueError('Una assignació no correspon a les candidates congelades')
            window = selected[0]
            key = window['id']
            evidence.write(json.dumps({
                'window_id': key, **assignment,
                'timestamp_s': trace['context']['timestamp_s'],
                'candidates': [dict(candidate_id=c['candidate_id'],
                                    measurement=c['measurement'],
                                    source_detection_ids=c['source_detection_ids'])
                               for c in candidates],
            })+'\n')
            if not args.clips and index not in samples[key]:
                continue
            image = reader.get(index).to_ndarray(format='bgr24')
            tile = panel(image,candidates,ids,window['crop'],index,
                         set(window['focus_ids']),args.show_candidates)
            if args.clips:
                writers[key].write(tile)
            if index in samples[key]:
                panels[key].append(tile)
        if index+1 != len(assignments):
            raise ValueError('La traça de candidates és incompleta')
    for key,tiles in panels.items():
        if len(tiles) != len(samples[key]):
            raise ValueError('Falten mostres a la làmina')
        tiles += [np.zeros_like(tiles[0])]*(len(tiles)%2)
        sheet = np.vstack([np.hstack(tiles[i:i+2]) for i in range(0,len(tiles),2)])
        if not cv2.imwrite(str(args.output/(key+'.jpg')),sheet,[cv2.IMWRITE_JPEG_QUALITY,90]):
            raise ValueError(f'No es pot escriure la làmina de {key}')


def main():
    """Valida el manifest i publica làmines i clips en una carpeta nova."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('catalog',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--clips',action='store_true')
    parser.add_argument('--show-candidates',action='store_true')
    parser.add_argument('--run',type=Path,default=ROOT/'runs/calibration/trampoline-silhouette-v1')
    parser.add_argument('--source',type=Path,default=ROOT/'runs/calibration/identity-continuity-v1')
    parser.add_argument('--dataset',type=Path,default=ROOT/'data/calibration-v1')
    args = parser.parse_args()
    cv2.setNumThreads(1)
    catalog = read_json(args.catalog)
    windows = catalog['windows']
    if len({w['id'] for w in windows})!=len(windows):
        raise ValueError('IDs de finestra repetits')
    corpus = {c['case_id']:c for c in read_json(args.dataset/'corpus.json')['cases']}
    cases = {window['case_id'] for window in windows}
    source = catalog['source']
    if cases != set(source['cases']) or cases & {item['case_id'] for item in catalog['reserve']}:
        raise ValueError('Els vídeos del catàleg i de la reserva són inconsistents')
    assignments = read_assignments(args.run,source)
    args.output.mkdir(parents=True,exist_ok=False)
    with (args.output/'review-frames.jsonl').open('w',encoding='utf-8') as evidence:
        for case in sorted(cases):
            render_case(case,[w for w in windows if w['case_id']==case],assignments[case],
                        corpus,source['cases'][case],args,evidence)
    atomic_json(args.output/'completed.json',{
        'catalog_sha256':sha256(args.catalog),'renderer_sha256':sha256(Path(__file__)),
        'source':source,
        'rendered_clips':args.clips,
        'show_candidates':args.show_candidates,
        'artifacts':artifacts(args.output,sorted(args.output.iterdir())),
    })


if __name__=='__main__':
    main()
