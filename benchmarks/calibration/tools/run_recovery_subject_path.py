"""Contrasta el camí geomètric del gimnasta amb un tracker i una auditoria congelats."""

import argparse
from collections import Counter
from contextlib import closing
from itertools import pairwise
import json
import math
from pathlib import Path

import cv2
import numpy as np

from benchmarks.calibration.engine.common import artifacts, atomic_json, inside, read_json, sha256, verify_artifacts, verify_file
from benchmarks.calibration.tools.review_recovery_cases import ROOT
from trampoline_vision.ingestion.recovery import load_tracking_trace
from trampoline_vision.ingestion.video import probe_video
from trampoline_vision.ingestion.video_frames import VideoFrameReader
from trampoline_vision.recovery import subject_path
from trampoline_vision.recovery.subject_path import SubjectCandidate, SubjectPathConfig, TemporalGraph


METHODS = ('tracker', 'hungarian', 'graph')
PANEL_SIZE = (240, 270)
TILE_HEIGHT = PANEL_SIZE[1] + 26
COLORS = ((90, 200, 255), (150, 215, 80), (230, 90, 235))


def unpack_trace(trace):
    """En conserva la geometria i tots els IDs observats, amb les candidates lliures."""
    frames, geometry = [], {}
    for row in trace.frames:
        frame = row.context.frame_index
        assigned = {t.candidate_id: t.track_id for t in row.tracks if t.evidence == 'observed'}
        candidates = []
        for item in row.candidates:
            cid = item.candidate.candidate_id
            box = item.candidate.measurement.bbox
            geometry[cid] = box
            candidates.append(SubjectCandidate(
                frame, cid, assigned.get(cid), (box.x_min + box.x_max)/2, (box.y_min + box.y_max)/2,
                math.sqrt((box.x_max - box.x_min)*(box.y_max - box.y_min)),
            ))
        if len(candidates) > 12:
            raise ValueError('Pressupost de candidates del replay superat')
        frames.append(candidates)
    return frames, geometry


def seeded_baselines(frames, seed, report, fragments):
    """Selecciona l’ID original i la cadena hongaresa que contenen la mateixa caixa inicial."""
    by_fragment = {item['fragment_id']: item for item in fragments}
    seed_frame, seed_id = seed['frame'], seed['track_id']
    start = next(item['fragment_id'] for item in fragments if item['track_id'] == seed_id
                 and item['first_frame_index'] <= seed_frame <= item['last_frame_index'])
    hypothesis = next(item for item in report['actor_hypotheses'] if start in item['fragment_ids'])
    wanted = {}
    for fid in hypothesis['fragment_ids']:
        item = by_fragment[fid]
        for index in range(max(seed_frame, item['first_frame_index']), item['last_frame_index']+1):
            if index in wanted:
                raise ValueError('Dos fragments de la mateixa cadena coincideixen')
            wanted[index] = item['track_id']
    return {
        'tracker': {c.frame: c for row in frames[seed_frame:] for c in row if c.track_id == seed_id},
        'hungarian': {c.frame: c for row in frames[seed_frame:] for c in row if c.track_id
                      and wanted.get(c.frame) == c.track_id},
    }


def label(candidate, anchors):
    """Classifica només les caixes d’actor etiquetades explícitament al catàleg."""
    if candidate is None:
        return 'gap'
    role = anchors.get(candidate.candidate_id)
    if role in ('gymnast', 'mixed', 'other_actor'):
        return role
    if role in ('judge', 'assistant', 'audience'):
        return 'other_actor'
    return 'pending_visual_review'


def compare_windows(windows, methods, geometry_focus, decisions, visual_roles):
    """Avalua observacions i parells, deixant pendents les caixes encara sense revisar."""
    results = []
    for window in windows:
        by_frame = {}
        for anchor in window['anchors']:
            row = by_frame.setdefault(anchor['frame'], {})
            if anchor['candidate_id'] is not None:
                row[anchor['candidate_id']] = anchor['role']
        for index, roles in by_frame.items():
            for candidate in (path.get(index) for path in methods.values()):
                if candidate is not None and candidate.candidate_id in visual_roles:
                    cid = candidate.candidate_id
                    if cid in roles and roles[cid] != visual_roles[cid]:
                        raise ValueError('Discrepància entre les dues revisions visuals')
                    roles[cid] = visual_roles[cid]
        status = {
            index: {method: label(methods[method].get(index), values) for method in METHODS}
            for index, values in sorted(by_frame.items())
        }
        gymnast = sorted(index for index, values in by_frame.items() if 'gymnast' in values.values())
        pairs = []
        for start, end in pairwise(gymnast):
            result = {}
            for method in METHODS:
                labels = {status[start][method], status[end][method]}
                if labels == {'gymnast'}:
                    result[method] = 'verified_endpoints'
                elif labels <= {'gymnast', 'pending_visual_review'}:
                    result[method] = 'pending_visual_review'
                else:
                    result[method] = 'failed_endpoints'
            pairs.append({'frames': [start, end], 'methods': result})
        scored = {
            'window_id': window['id'], 'type': window['type'], 'case_id': window['case_id'],
            'anchors': {i: {'labels': states, 'graph_ambiguous': decisions[i]['ambiguous'],
                            'candidate_ids': {m: methods[m][i].candidate_id if i in methods[m] else None
                                              for m in METHODS}} for i, states in status.items()},
            'gymnast_pairs': pairs,
        }
        focus = geometry_focus.get(window['id'])
        if focus:
            before, after = (focus[key]['frame'] for key in ('before', 'after'))
            scored['focus_pair'] = {'frames': [before, after], 'before': status[before], 'after': status[after]}
        results.append(scored)
    return results


def path_rows(frame_count, seed_frame, methods, solution, margin):
    """Publica el camí, els buits i les alternatives properes al mínim global."""
    rows = {}
    for index in range(seed_frame, frame_count):
        options = {**solution.candidate_costs.get(index, {})}
        if index in solution.gap_costs:
            options['gap'] = solution.gap_costs[index]
        deltas = {choice: max(0.0, cost-solution.cost) for choice, cost in options.items()}
        nearby = [choice for choice, delta in sorted(deltas.items(), key=lambda item: item[1])
                  if delta <= margin + 1e-10]
        best = solution.observations.get(index)
        assert nearby and (best.candidate_id if best else 'gap') in nearby
        rows[index] = {
            'frame': index, 'ambiguous': len(nearby) > 1, 'nearby_choices': nearby,
            'graph_cost_deltas': deltas,
            'selection': {method: methods[method][index].candidate_id if index in methods[method] else None
                          for method in METHODS},
            'tracking_ids': {method: methods[method][index].track_id if index in methods[method] else None
                             for method in METHODS},
        }
    return rows


def draw_box(tile, bbox, color, image):
    """Dibuixa una caixa al panell amb la mateixa escala que els píxels originals."""
    height, width = image.shape[:2]
    x_min, x_max = [round(v*PANEL_SIZE[0]/width) for v in (bbox.x_min, bbox.x_max)]
    y_min, y_max = [26+round(v*PANEL_SIZE[1]/height) for v in (bbox.y_min, bbox.y_max)]
    cv2.rectangle(tile, (x_min, y_min), (x_max, y_max), color, 2)


def tile_for(image, title):
    """Prepara una còpia dels píxels amb una capçalera de revisió."""
    tile = np.zeros((TILE_HEIGHT, PANEL_SIZE[0], 3), np.uint8)
    tile[26:] = cv2.resize(image, PANEL_SIZE, interpolation=cv2.INTER_AREA)
    cv2.putText(tile, title, (4, 17), cv2.FONT_HERSHEY_SIMPLEX, .47, (245, 245, 245), 1, cv2.LINE_AA)
    return tile


def render_windows(video, windows, geometry, rows, output):
    """Genera clips comparables i una làmina de sis àncores per vídeo."""
    samples = []
    with closing(VideoFrameReader(video)) as reader:
        for window in windows:
            review_frame = min(a['frame'] for a in window['anchors'] if a['role'] == 'gymnast')
            path = output / f"{window['id']}.mp4"
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), video.fps,
                                     (PANEL_SIZE[0]*4, TILE_HEIGHT))
            if not writer.isOpened():
                raise ValueError(f'No es pot escriure el clip {path}')
            try:
                for index in range(window['start'], window['stop']):
                    image = reader.get(index).to_ndarray(format='bgr24')
                    row = rows[index]
                    tiles = [tile_for(image, f'#{index} Original')]
                    for name, method, color in zip(('Tracker', 'Hongares', 'Graf'), METHODS, COLORS, strict=True):
                        cid = row['selection'][method]
                        tid = row['tracking_ids'][method]
                        tag = 'buit' if cid is None else f"{cid.rsplit(':', 1)[-1]} | ID {tid or '-'}"
                        if method == 'graph' and row['ambiguous']:
                            tag += ' ?'
                        tile = tile_for(image, f'{name} {tag}')
                        if cid is not None:
                            draw_box(tile, geometry[cid], color, image)
                        tiles.append(tile)
                    writer.write(np.hstack(tiles))
                    if index == review_frame:
                        reference = tile_for(image, f'#{index} Referencia')
                        for anchor in window['anchors']:
                            if anchor['frame'] == index and anchor['role'] == 'gymnast':
                                draw_box(reference, geometry[anchor['candidate_id']], (80, 230, 85), image)
                        samples.append(np.hstack((reference, tiles[-1])))
            finally:
                writer.release()
    blocks = [np.hstack(samples[i:i+2]) for i in range(0, len(samples), 2)]
    if not cv2.imwrite(str(output / 'graf-vs-referencia.jpg'), np.vstack(blocks)):
        raise ValueError('No es pot escriure la làmina de contrast')


def summary_counts(windows):
    """Agrega les àncores, els parells i els casos sense verificació visual."""
    return {
        method: {
            'catalog_frames': dict(Counter(a['labels'][method] for w in windows for a in w['anchors'].values())),
            'anchor_pairs': dict(Counter(pair['methods'][method] for w in windows for pair in w['gymnast_pairs'])),
        } for method in METHODS
    }


def run(plan_path, audit_root, dataset, output):
    """Verifica les entrades, resol els tres camins i publica traces i revisió."""
    plan = read_json(plan_path)
    for name in ('catalog', 'simulation', 'visual_review'):
        verify_file(inside(ROOT, plan[name]), plan[f'{name}_sha256'])
    verify_file(audit_root / 'completed.json', plan['audit_manifest_sha256'])
    verify_artifacts(audit_root, read_json(audit_root / 'completed.json')['artifacts'])
    catalog = read_json(inside(ROOT, plan['catalog']))
    visual = read_json(inside(ROOT, plan['visual_review']))
    if visual['catalog_sha256'] != plan['catalog_sha256']:
        raise ValueError('La revisió addicional correspon a un altre catàleg')
    config = SubjectPathConfig(**read_json(inside(ROOT, plan['simulation']))['settings'])
    references = read_json(audit_root / 'summary.json')
    focus = {w['window_id']: w['focus_pair'] for w in references['windows'] if 'focus_pair' in w}
    if references['source'] != catalog['source'] or set(plan['seeds']) != set(catalog['source']['cases']):
        raise ValueError('Els orígens de les tres estratègies han de coincidir')
    corpus = {item['case_id']: item for item in read_json(dataset / 'corpus.json')['cases']}
    output.mkdir(parents=True, exist_ok=False)
    details, case_data = [], {}
    cv2.setNumThreads(1)
    for case, seed in plan['seeds'].items():
        windows = [w for w in catalog['windows'] if w['case_id'] == case]
        video_path = inside(dataset, corpus[case]['path'])
        verify_file(video_path, catalog['source']['cases'][case]['video_sha256'])
        video = probe_video(video_path, case)
        if not math.isclose(video.fps, 30) or any(not math.isclose(dt, 1/30, abs_tol=1e-6) for dt in video.frame_durations_s):
            raise ValueError('La prova assumeix 30 fotogrames per segon amb pas constant')
        source = inside(audit_root, case)
        trace = load_tracking_trace(source / 'tracking.frames.jsonl', source / 'tracking.json', video).trace
        frames, geometry = unpack_trace(trace)
        if seed['frame'] >= min(w['start'] for w in windows) or not any(
            c.candidate_id == seed['candidate_id'] and c.track_id == seed['track_id'] for c in frames[seed['frame']]
        ):
            raise ValueError('La caixa inicial ha de ser observada i anterior a les finestres puntuades')
        baselines = seeded_baselines(frames, seed, read_json(source / 'audit.json'),
                                     read_json(source / 'fragments.json')['fragments'])
        graph = TemporalGraph(frames, seed['frame'], seed['candidate_id'], config).solve()
        methods = {**baselines, 'graph': graph.observations}
        if any(path[seed['frame']].candidate_id != seed['candidate_id'] for path in methods.values()):
            raise ValueError('Les tres estratègies han de començar a la mateixa caixa')
        rows = path_rows(len(frames), seed['frame'], methods, graph, config.ambiguity_margin)
        case_windows = compare_windows(windows, methods, focus, rows, visual['candidate_roles'][case])
        chosen = {cid for entry in case_windows for anchor in entry['anchors'].values()
                  for cid in anchor['candidate_ids'].values()}
        if not visual['candidate_roles'][case].keys() <= chosen:
            raise ValueError('La revisió conté caixes que cap estratègia ha seleccionat')
        details.extend(case_windows)
        dest = output / case
        dest.mkdir()
        with (dest / 'path.jsonl').open('x', encoding='utf-8') as stream:
            for row in rows.values():
                stream.write(json.dumps(row, allow_nan=False)+'\n')
        render_windows(video, windows, geometry, rows, dest)
        case_data[case] = {
            'seed': seed, 'frames_loaded': len(frames), 'frames_compared': len(rows),
            'graph_cost': graph.cost, 'graph_ambiguous_frames': sum(row['ambiguous'] for row in rows.values()),
            'observations': {m: len(path) for m, path in methods.items()},
            'scores': summary_counts(case_windows),
        }
        print(f'{case}: {case_data[case]["observations"]}', flush=True)
    atomic_json(output / 'summary.json', {
        'plan': plan, 'plan_sha256': sha256(plan_path),
        'runner_sha256': sha256(__file__), 'solver_sha256': sha256(subject_path.__file__),
        'scores': summary_counts(details), 'cases': case_data, 'windows': details,
    })
    atomic_json(output / 'completed.json', {'artifacts': artifacts(output, sorted(p for p in output.rglob('*') if p.is_file()))})


def main():
    """Executa un pla de comparació amb els artefactes congelats del banc."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--audit', type=Path, default=ROOT / 'runs/calibration/recovery-geometry-v1-reviewed')
    parser.add_argument('--dataset', type=Path, default=ROOT / 'data/calibration-v1')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.plan, args.audit, args.dataset, args.output)


if __name__ == '__main__':
    main()
