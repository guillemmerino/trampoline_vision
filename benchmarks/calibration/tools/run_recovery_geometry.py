"""Executa l’auditoria geomètrica existent sobre traces experimentals congelades."""

import argparse
from collections import Counter
from itertools import pairwise
import json
from pathlib import Path
import time

from benchmarks.calibration.engine.common import artifacts, atomic_json, inside, read_json, sha256, verify_file
from benchmarks.calibration.tools.review_recovery_cases import ROOT, read_assignments
from trampoline_vision.application.recovery_audit import audit_tracking_recovery
from trampoline_vision.ingestion.recovery import load_tracking_trace
from trampoline_vision.ingestion.video import probe_video
from trampoline_vision.recovery.pipeline import prepare_recovery
from trampoline_vision.results.recovery import diagnostics


OTHER_ROLES = {'assistant', 'judge', 'audience'}


def adapt_frame(record, assignment, run_id, live):
    """Conserva caixes, IDs i prediccions, i tradueix els canvis d’estat públic."""
    if record['context']['frame_index'] != assignment['frame_index']:
        raise ValueError('Les dues traces tenen índexs diferents')
    time_s = record['context']['timestamp_s']
    candidates = {item['candidate_id']: item for item in record['candidates']}
    observed = {str(tid): cid for cid, tid in assignment['observed'].items()}
    predicted = {str(tid) for tid in assignment['predicted_ids']}
    if observed.keys() & predicted or not predicted <= live.keys() or not set(observed.values()) <= candidates.keys():
        raise ValueError('Evidència experimental incompatible amb el contracte de tracking')
    for candidate in candidates.values():
        # El motiu d’exclusió depèn del tracker anterior, encara que la caixa sigui comuna.
        candidate.pop('unassigned_reason', None)
    tracks, events, next_live = [], [], {}
    for tid in sorted(live.keys() | observed.keys()):
        candidate_id = observed.get(tid)
        if candidate_id is not None:
            state, evidence = 'active', 'observed'
            bbox = candidates[candidate_id]['measurement']['bbox']
            last_s = time_s
            kind = 'confirmed' if tid not in live else 'recovered' if live[tid][0] == 'lost' else None
        else:
            previous_state, last_s = live[tid]
            # La traça publica IDs predits sense geometria. La retirada és la primera absència.
            state = 'lost' if tid in predicted else 'finished'
            evidence, bbox = 'predicted', None
            kind = state if state != previous_state else None
        tracks.append(dict(track_id=tid, state=state, evidence=evidence, bbox=bbox,
                           candidate_id=candidate_id, last_observed_timestamp_s=last_s))
        if kind is not None:
            events.append(dict(track_id=tid, kind=kind, timestamp_s=time_s))
        if state != 'finished':
            next_live[tid] = state, last_s
    unassigned = sorted(candidates.keys() - set(observed.values()))
    return dict(record, run_id=run_id, tracks=tracks, events=events, unassigned_candidate_ids=unassigned), next_live


def adapt_case(case, video, frozen_frames, assignments, provenance, target):
    """Escriu l’exportació canònica, amb procedència explícita i cobertura completa."""
    run_id = f"{case}:velocity_soft_yolo:{provenance['assignments_sha256'][:16]}"
    tracks_path = target / 'tracking.frames.jsonl'
    report_path = target / 'tracking.json'
    live = {}
    totals = Counter()
    with frozen_frames.open(encoding='utf-8') as source, tracks_path.open('x', encoding='utf-8') as stream:
        for raw, assignment in zip(source, assignments, strict=True):
            frame, live = adapt_frame(json.loads(raw), assignment, run_id, live)
            totals.update(frames=1, source_detections=frame['source_detections'],
                          candidates=len(frame['candidates']), observed_track_samples=len(assignment['observed']),
                          predicted_track_samples=len(assignment['predicted_ids']),
                          unassigned_candidates=len(frame['unassigned_candidate_ids']))
            stream.write(json.dumps(frame, ensure_ascii=False, allow_nan=False) + '\n')
    atomic_json(report_path, {
        'schema_version': '1.0', 'task': 'track_recorded_detections', 'run_id': run_id, 'case_id': case,
        'range': dict(first_frame_index=0, last_frame_index=video.frame_count-1, warmup_frames=0,
                      tracker_started_at_frame=0, source_start_s=0, source_end_s=video.duration_s),
        'inputs': {'video': {'path': str(video.path), 'sha256': provenance['cases'][case]['video_sha256']}},
        'artifacts': {'frames_jsonl': tracks_path.name, 'frames_sha256': sha256(tracks_path)},
        'totals': dict(totals),
        'right_censored_track_ids': sorted(live),
        'derived_from': {'variant': provenance['variant'], 'assignments_sha256': provenance['assignments_sha256'],
                         'candidates_sha256': provenance['cases'][case]['candidates_sha256'],
                         'prediction_geometry': 'unavailable_in_experimental_trace',
                         'finished_event': 'first_absent_frame_after_public_track'},
    })
    return report_path, tracks_path


def read_anchors(windows, prepared):
    """Enllaça cada àncora del catàleg amb l’observació i el fragment verificats."""
    observations = {(sample.context.frame_index, fragment.track_id): (fragment.fragment_id, sample.track.candidate_id)
                    for fragment in prepared.fragments for sample in fragment.samples}
    by_window = {}
    for window in windows:
        anchors = {}
        for item in window['anchors']:
            tid = item['track_id']
            if tid is None:
                continue
            fragment, candidate = observations[item['frame'], str(tid)]
            if candidate != item['candidate_id']:
                raise ValueError(f"Àncora incompatible amb la caixa observada: {window['id']}")
            anchors[item['frame'], tid] = dict(item, fragment_id=fragment)
        by_window[window['id']] = anchors
    return by_window


def compare_pair(before, after, chains, edges, actor_anchors):
    """Contrasta l’ID original i la cadena provisional per a dues àncores."""
    first, last = before['fragment_id'], after['fragment_id']
    chain = chains[first]
    path = chain[chain.index(first):chain.index(last)+1] if last in chain else []
    conflicts = [a for a in actor_anchors if a['role'] in OTHER_ROLES
                 and a['fragment_id'] in path and before['frame'] < a['frame'] < after['frame']]
    return {
        'before': before, 'after': after, 'same_tracker_id': before['track_id'] == after['track_id'],
        'same_fragment': first == last, 'same_recovery_chain': last in chain,
        'path': path, 'direct_edge': edges.get((first, last)),
        'intermediate_other_actor_anchors': conflicts,
    }


def mixed_chain_evidence(hypotheses, anchors):
    """Registra cadenes amb àncores incompatibles fins i tot entre finestres diferents."""
    by_fragment = {}
    for anchor in anchors:
        by_fragment.setdefault(anchor['fragment_id'], []).append(anchor)
    conflicts = []
    for hypothesis in hypotheses:
        fragments = hypothesis['fragment_ids']
        observed = [anchor for fid in fragments for anchor in by_fragment.get(fid, ())]
        gymnast = [a for a in observed if a['role'] == 'gymnast']
        other = [a for a in observed if a['role'] in OTHER_ROLES]
        if gymnast and other:
            conflicts.append({
                'hypothesis_id': hypothesis['hypothesis_id'],
                'fragment_ids': fragments,
                'gymnast_anchors': gymnast,
                'other_actor_anchors': other,
                'joins_different_tracker_ids': any(a['track_id'] != b['track_id'] for a in gymnast for b in other),
            })
    return conflicts


def evaluate_windows(windows, plan, prepared, audit, links):
    """Mesura els extrems i els avisos de transferència sobre la primera revisió visual."""
    by_window = read_anchors(windows, prepared)
    all_anchors = [a for values in by_window.values() for a in values.values()]
    chains = {fid: h['fragment_ids'] for h in audit['actor_hypotheses'] for fid in h['fragment_ids']}
    edges = {(link['source_fragment_id'], link['target_fragment_id']): link
             for link in links}
    jumps = audit['diagnostics']['review']['possible_internal_discontinuities']
    spans = {fragment.fragment_id: [fragment.samples[0].context.frame_index, fragment.samples[-1].context.frame_index]
             for fragment in prepared.fragments}
    results = []
    for window in windows:
        key, kind = window['id'], window['type']
        anchors = by_window[key]
        gym_by_frame = {}
        for item in anchors.values():
            if item['role'] == 'gymnast':
                gym_by_frame.setdefault(item['frame'], []).append(item)
        pairs = []
        for start, stop in pairwise(sorted(gym_by_frame)):
            options = [compare_pair(before, after, chains, edges, all_anchors)
                       for before in gym_by_frame[start] for after in gym_by_frame[stop]]
            pairs.append({'frames': [start, stop], 'options': options,
                          'same_tracker_id': any(p['same_tracker_id'] for p in options),
                          'same_recovery_chain': any(p['same_recovery_chain'] for p in options)})
        result = {'window_id': key, 'case_id': window['case_id'], 'type': kind, 'gymnast_pairs': pairs,
                  'gymnast_anchors': sorted(gym_by_frame)}
        if kind in {'gap', 'transfer'}:
            section = 'gap_pairs' if kind == 'gap' else 'transfer_pairs'
            start, stop = (anchors[tuple(anchor)] for anchor in plan[section][key])
            if start['role'] != 'gymnast' or (stop['role'] == 'gymnast') != (kind == 'gap'):
                raise ValueError(f'Rols incompatibles amb l’episodi {key}')
            pair = compare_pair(start, stop, chains, edges, all_anchors)
            result['focus_pair'] = pair
            result['endpoint_fragments'] = {a['fragment_id']: spans[a['fragment_id']] for a in (start, stop)}
            if kind == 'transfer':
                prefix = f"fragment:{start['track_id']}:"
                result['internal_jumps_in_transfer_bracket'] = [
                    jump for jump in jumps if jump['fragment_id'].startswith(prefix)
                    and start['frame'] < jump['frame_index'] <= stop['frame']]
        results.append(result)
    return results, mixed_chain_evidence(audit['actor_hypotheses'], all_anchors)


def run(plan_path, dataset, assignments_run, candidates_run, output):
    """Executa el perfil congelat, comprova l’adaptació i desa l’avaluació provisional."""
    started = time.perf_counter()
    plan = read_json(plan_path)
    catalog_path = inside(ROOT, plan['catalog'])
    verify_file(catalog_path, plan['catalog_sha256'])
    catalog = read_json(catalog_path)
    provenance = catalog['source']
    profile = inside(ROOT, plan['profile'])
    verify_file(profile, plan['profile_sha256'])
    corpus = {item['case_id']: item for item in read_json(dataset / 'corpus.json')['cases']}
    assignments = read_assignments(assignments_run, provenance)
    output.mkdir(parents=True, exist_ok=False)
    all_windows, case_totals, mixed_chains = [], {}, {}
    for case, expected in sorted(provenance['cases'].items()):
        windows = [w for w in catalog['windows'] if w['case_id'] == case]
        video_path = inside(dataset, corpus[case]['path'])
        frozen_frames = inside(candidates_run, f'{case}/botsort.frames.jsonl')
        verify_file(video_path, expected['video_sha256'])
        verify_file(frozen_frames, expected['candidates_sha256'])
        video = probe_video(video_path, case)
        dest = output / case
        dest.mkdir()
        report, tracks = adapt_case(case, video, frozen_frames, assignments[case], provenance, dest)
        audit = audit_tracking_recovery(report, dest / 'audit.json', config_file=profile)
        prepared = prepare_recovery(load_tracking_trace(tracks, report, video).trace)
        atomic_json(dest / 'fragments.json', diagnostics(prepared))
        with (dest / 'audit.links.jsonl').open(encoding='utf-8') as stream:
            evaluated, mixed_chains[case] = evaluate_windows(windows, plan, prepared, audit, map(json.loads, stream))
        all_windows.extend(evaluated)
        case_totals[case] = {**audit['totals'], 'frames': video.frame_count}
        print(f"{case}: {audit['totals']['selected_link_proposals']} unions proposades", flush=True)
    pairs = [pair for window in all_windows for pair in window['gymnast_pairs']]
    atomic_json(output / 'summary.json', {
        'plan': plan, 'plan_sha256': sha256(plan_path), 'profile_sha256': sha256(profile),
        'adapter_sha256': sha256(Path(__file__)), 'source': provenance,
        'references': 'provisional_agent_anchors', 'applied': False, 'elapsed_s': time.perf_counter()-started,
        'cases': case_totals,
        'chains_with_gymnast_and_other_actor_anchors': mixed_chains,
        'gymnast_anchor_pairs': {'total': len(pairs), 'same_tracker_id': sum(p['same_tracker_id'] for p in pairs),
                                 'same_recovery_chain': sum(p['same_recovery_chain'] for p in pairs),
                                 'gains': sum(p['same_recovery_chain'] and not p['same_tracker_id'] for p in pairs),
                                 'losses': sum(p['same_tracker_id'] and not p['same_recovery_chain'] for p in pairs)},
        'windows': all_windows,
    })
    atomic_json(output / 'completed.json', {'artifacts': artifacts(output, sorted(p for p in output.rglob('*') if p.is_file()))})


def main():
    """Llegeix el pla del benchmark i executa amb el corpus i els runs indicats."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--dataset', type=Path, default=ROOT / 'data/calibration-v1')
    parser.add_argument('--assignments', type=Path, default=ROOT / 'runs/calibration/trampoline-silhouette-v1')
    parser.add_argument('--candidates', type=Path, default=ROOT / 'runs/calibration/identity-continuity-v1')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.plan, args.dataset, args.assignments, args.candidates, args.output)


if __name__ == '__main__':
    main()
