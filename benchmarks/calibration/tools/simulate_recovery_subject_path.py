"""Simula la recuperació d’un gimnasta en un graf temporal amb escenes sintètiques."""

import argparse
from dataclasses import dataclass
from itertools import pairwise
import math
from pathlib import Path

from benchmarks.calibration.engine.common import atomic_json, read_json, sha256


@dataclass(frozen=True)
class Candidate:
    """Observació geomètrica sintètica amb l’ID que li ha donat el tracker."""

    frame: int
    name: str
    track_id: int
    x: float
    y: float
    scale: float


@dataclass(frozen=True)
class Settings:
    """Pesos compartits per les decisions locals i el camí global."""

    distance_weight: float
    velocity_weight: float
    scale_weight: float
    id_change_cost: float
    missing_frame_cost: float
    max_missing_frames: int
    ambiguity_margin: float


def velocity(before, after):
    """Calcula la velocitat mitjana per fotograma entre dues observacions."""
    elapsed = after.frame - before.frame
    return (after.x - before.x) / elapsed, (after.y - before.y) / elapsed


def link_cost(previous, current, target, settings):
    """Puntua l’aresta amb el moviment de les dues últimes observacions."""
    movement = velocity(current, target)
    scale = math.sqrt(current.scale * target.scale)
    speed = settings.distance_weight * math.hypot(*movement) / scale
    change = 0.0
    if previous is not None:
        change = settings.velocity_weight * math.dist(velocity(previous, current), movement) / scale
    size = settings.scale_weight * abs(math.log(target.scale / current.scale))
    identity = settings.id_change_cost if current.track_id != target.track_id else 0.0
    missing = (target.frame - current.frame - 1) * settings.missing_frame_cost
    return {
        'movement': speed,
        'velocity_change': change,
        'scale_change': size,
        'id_change': identity,
        'missing_frames': missing,
    }


def greedy(frames, settings):
    """Compara cada fotograma amb la millor opció immediata i el cost d’un buit."""
    path = [frames[0][0]]
    for index, candidates in enumerate(frames[1:], 1):
        current = path[-1]
        if index - current.frame - 1 > settings.max_missing_frames:
            break
        previous = path[-2] if len(path) > 1 else None
        scores = []
        for candidate in candidates:
            costs = link_cost(previous, current, candidate, settings)
            # Els buits anteriors són compartits per les dues decisions immediates.
            scores.append((sum(costs.values()) - costs['missing_frames'], candidate))
        if scores:
            cost, best = min(scores, key=lambda item: item[0])
            if cost < settings.missing_frame_cost:
                path.append(best)
    return path


def solve(frames, settings, forced_frame=None, choice=None):
    """Resol el camí global i, opcionalment, fixa una caixa o un buit en un fotograma."""
    seed = (None, frames[0][0])
    states = [{} for _ in frames]
    states[0][seed] = 0.0
    predecessor = {}
    for index, entries in enumerate(states):
        stop = min(len(frames), index + settings.max_missing_frames + 2)
        if forced_frame is not None and choice is not None and index < forced_frame:
            stop = min(stop, forced_frame + 1)
        for state, cost in entries.items():
            previous, current = state
            for future in range(index + 1, stop):
                for target in frames[future]:
                    if future == forced_frame and target.name != choice:
                        continue
                    key = current, target
                    total = cost + sum(link_cost(previous, current, target, settings).values())
                    if total < states[future].get(key, math.inf):
                        states[future][key] = total
                        predecessor[key] = state
    ends = (
        (cost + (len(frames) - i - 1) * settings.missing_frame_cost, state)
        for i, entries in enumerate(states)
        if choice is None or i >= forced_frame
        for state, cost in entries.items()
    )
    cost, state = min(ends, key=lambda item: item[0], default=(math.inf, None))
    path = []
    while state is not None:
        path.append(state[1])
        state = predecessor.get(state)
    return list(reversed(path)), cost


def summarize(path, useful, settings):
    """Calcula usabilitat, confusions, salts i cost a partir del camí observat."""
    chosen = {item.frame: item.name for item in path}
    links = []
    previous = None
    for before, after in pairwise(path):
        costs = link_cost(previous, before, after, settings)
        links.append({
            'from': before.frame, 'to': after.frame,
            'from_id': before.track_id, 'to_id': after.track_id,
            'skipped_frames': list(range(before.frame + 1, after.frame)),
            'costs': costs,
        })
        previous = before
    tail = (len(useful) - path[-1].frame - 1) * settings.missing_frame_cost
    return {
        'chosen': [chosen.get(frame) for frame in range(len(useful))],
        'tracker_ids': {item.frame: item.track_id for item in path},
        'cost': sum(sum(link['costs'].values()) for link in links) + tail,
        'useful_observations': sum(name in useful[frame] for frame, name in chosen.items()),
        'wrong_actor_frames': [frame for frame, name in chosen.items() if name not in useful[frame]],
        'frames_without_observation': [i for i in range(len(useful)) if i not in chosen],
        'links': links,
    }


def compare_choices(frames, useful, settings, frame, best_cost):
    """Compara camins complets i usa les etiquetes sintètiques només per interpretar el marge."""
    choices = [box.name for box in frames[frame]] + [None]
    results = []
    for name in choices:
        path, cost = solve(frames, settings, frame, name)
        if math.isfinite(cost):
            results.append({
                'candidate': name,
                'tracker_id': next((box.track_id for box in frames[frame] if box.name == name), None),
                'complete_path_cost': cost,
                'margin': max(0.0, cost - best_cost),
                'useful_reference': name in useful[frame],
                'path': [{'frame': box.frame, 'candidate': box.name} for box in path],
            })
    results.sort(key=lambda result: result['complete_path_cost'])
    close = [r for r in results if r['margin'] <= settings.ambiguity_margin]
    decision = 'ambiguous' if len(close) > 1 else 'gap' if close[0]['candidate'] is None else 'selected'
    return {
        'frame': frame,
        'decision': decision,
        'equally_useful_boxes': len(close) > 1 and all(r['useful_reference'] for r in close),
        'options': results,
    }


def run_scenario(scenario, settings):
    """Executa les dues estratègies amb la mateixa observació inicial i els mateixos costos."""
    frames = [[Candidate(i, *row) for row in records] for i, records in enumerate(scenario['frames'])]
    useful = scenario['useful']
    if len(frames[0]) != 1 or len(useful) != len(frames):
        raise ValueError('Cal una observació inicial i una referència sintètica per fotograma')
    for candidates, labels in zip(frames, useful, strict=True):
        names = {box.name for box in candidates}
        if len(names) != len(candidates) or len(candidates) > 12 or not set(labels) <= names:
            raise ValueError('El fotograma sintètic conté candidates o referències inconsistents')
    path, cost = solve(frames, settings)
    global_result = summarize(path, useful, settings)
    if not math.isclose(global_result['cost'], cost):
        raise RuntimeError('El cost del camí reconstruït difereix del mínim calculat')
    return {
        'id': scenario['id'],
        'description': scenario['description'],
        'greedy': summarize(greedy(frames, settings), useful, settings),
        'global': global_result,
        'review': [compare_choices(frames, useful, settings, i, cost) for i in scenario['inspect']],
    }


def main():
    """Executa el pla sintètic i publica un informe nou amb totes les opcions comparades."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    plan = read_json(args.plan)
    settings = Settings(**plan['settings'])
    results = [run_scenario(scenario, settings) for scenario in plan['scenarios']]
    args.output.mkdir(parents=True, exist_ok=False)
    atomic_json(args.output / 'summary.json', {
        'plan': plan, 'plan_sha256': sha256(args.plan), 'code_sha256': sha256(Path(__file__)),
        'scenarios': results,
    })


if __name__ == '__main__':
    main()
