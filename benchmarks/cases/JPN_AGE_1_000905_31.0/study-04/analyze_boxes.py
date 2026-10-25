"""Compara caixes YOLO amb les mateixes anotacions visuals aproximades de l'estudi anterior.

Les 25 caixes són un pilot dispers, no una veritat exhaustiva del vídeo.
L'assignació unívoca evita comptar una mateixa caixa per a dos actors.
"""

import argparse
from collections import defaultdict
import json
from pathlib import Path
from scipy.optimize import linear_sum_assignment


def iou(a, b):
    """Calcula el solapament espacial de dos rectangles xyxy originals."""
    inter = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
    return inter / union if union > 0 else 0


def xyxy(box):
    """Passa del contracte serialitzat al rectangle, sense ajustar-lo a l'anotació."""
    return [box[k] for k in ('x_min', 'y_min', 'x_max', 'y_max')]


def read_records(path):
    """Carrega el clip curt i rebutja índexs repetits o fora d'ordre."""
    records = {}
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            record = json.loads(line)
            index = record['context']['frame_index']
            if index != len(records):
                raise ValueError('Non-consecutive replay frames')
            records[index] = record
    return records


def evaluate(records, samples, threshold):
    """Mesura cobertura observada i IDs només als instants revisats; les prediccions no compten com deteccions."""
    grouped = defaultdict(list)
    for sample in samples:
        grouped[sample['frame_index']].append(sample)
    subjects, details, previous = {}, [], {}
    for index, annotations in sorted(grouped.items()):
        record = records[index]
        tracks = [t for t in record['tracks'] if t['evidence'] == 'observed']
        matrix = [[iou(a['bbox_xyxy'], xyxy(t['bbox'])) for t in tracks] for a in annotations]
        matches = {}
        if tracks:
            rows, columns = linear_sum_assignment(matrix, maximize=True)
            matches = {int(r): int(c) for r, c in zip(rows, columns) if matrix[r][c] >= threshold}
        for row, annotation in enumerate(annotations):
            subject = annotation['subject_id']
            metrics = subjects.setdefault(subject, {'samples': 0, 'box_available': 0, 'observed_matches': 0,
                                                     'id_changes_across_matches': 0, 'track_ids': set()})
            metrics['samples'] += 1
            best = max(record['candidates'], key=lambda c: iou(annotation['bbox_xyxy'], xyxy(c['measurement']['bbox'])))
            overlap = iou(annotation['bbox_xyxy'], xyxy(best['measurement']['bbox']))
            metrics['box_available'] += overlap >= threshold
            track = tracks[matches[row]] if row in matches else None
            if track:
                tid = track['track_id']
                metrics['observed_matches'] += 1
                metrics['track_ids'].add(tid)
                metrics['id_changes_across_matches'] += subject in previous and previous[subject] != tid
                previous[subject] = tid
            details.append({**annotation, 'candidate_iou': overlap, 'candidate_score': best['measurement']['score'],
                            'track_id': track['track_id'] if track else None,
                            'track_iou': iou(annotation['bbox_xyxy'], xyxy(track['bbox'])) if track else None})
    for item in subjects.values():
        item['track_ids'] = sorted(item['track_ids'])
    return {'threshold': threshold, 'subjects': subjects, 'details': details,
            'ids_seen_on_both_subjects': sorted(set(subjects['gymnast']['track_ids']) & set(subjects['rear_spotter']['track_ids']))}


def main():
    """Escriu un informe nou dels controls seleccionats, sense modificar els replays."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path, required=True)
    parser.add_argument('--case-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--variants', nargs='+', default=['ocsort_boxes', 'byte_boxes_high', 'byte_boxes_weak'])
    args = parser.parse_args()
    samples = json.loads((args.case_dir / 'study-03/review-boxes.json').read_text(encoding='utf-8'))['samples']
    output = {'variants': {}, 'limitations': ['sparse_approximate_review_boxes', 'no_dense_ground_truth', 'no_pose_quality_evaluation']}
    for name in args.variants:
        records = read_records(args.runs / f'{name}.frames.jsonl')
        output['variants'][name] = {str(threshold): evaluate(records, samples, threshold) for threshold in (.3, .5)}
        print(name, json.dumps({t: r['subjects'] for t, r in output['variants'][name].items()}))
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(output, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


if __name__ == '__main__':
    main()
