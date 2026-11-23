"""Camí experimental d’un sol subjecte en un graf temporal de caixes."""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SubjectCandidate:
    """Observació geomètrica d’un fotograma, amb ID original opcional."""

    frame: int
    candidate_id: str
    track_id: str | None
    x: float
    y: float
    scale: float


@dataclass(frozen=True)
class SubjectPathConfig:
    """Pesos de moviment i criteris d’ambigüitat del camí experimental."""

    distance_weight: float
    velocity_weight: float
    scale_weight: float
    id_change_cost: float
    missing_frame_cost: float
    max_missing_frames: int
    ambiguity_margin: float


@dataclass(frozen=True)
class SubjectPath:
    """Camí mínim i costos globals de les alternatives, inclòs el buit per fotograma."""

    cost: float
    observations: dict[int, SubjectCandidate]
    candidate_costs: dict[int, dict[str, float]]
    gap_costs: dict[int, float]


class TemporalGraph:
    """Representa cada estat per les seves dues observacions més recents."""

    def __init__(self, frames, seed_frame, seed_id, config):
        """Indexa les candidates des de la caixa inicial fins al final, a FPS constants."""
        if not 0 <= seed_frame < len(frames):
            raise ValueError('Fotograma inicial fora del vídeo')
        seed = [candidate for candidate in frames[seed_frame] if candidate.candidate_id == seed_id]
        if len(seed) != 1 or config.max_missing_frames < 0:
            raise ValueError('La caixa inicial ha de ser única i el límit de buit vàlid')
        self.nodes = seed + [candidate for row in frames[seed_frame+1:] for candidate in row]
        self.frame = np.array([node.frame for node in self.nodes])
        if self.frame[0] != seed_frame or (self.frame[1:] <= seed_frame).any():
            raise ValueError('Índexs de candidates incompatibles amb el punt inicial')
        self.centers = np.array([(node.x, node.y) for node in self.nodes])
        self.scales = np.array([node.scale for node in self.nodes])
        if not np.isfinite(self.centers).all() or not np.isfinite(self.scales).all() or (self.scales <= 0).any():
            raise ValueError('Geometria invàlida al graf temporal')
        track_codes = {value: index+1 for index, value in enumerate(sorted({
            node.track_id for node in self.nodes if node.track_id is not None
        }))}
        self.track = np.array([track_codes.get(node.track_id, 0) for node in self.nodes])
        jump = config.max_missing_frames + 1
        self.left = self.frame.searchsorted(self.frame - jump)
        self.first = self.frame.searchsorted(self.frame)
        self.after = self.frame.searchsorted(self.frame, side='right')
        self.right = self.frame.searchsorted(self.frame + jump, side='right')
        self.width = max(1, int(max(self.first - self.left)))
        self.tail = (len(frames) - 1 - self.frame) * config.missing_frame_cost
        self.frame_count = len(frames)
        self.config = config

    def transitions(self, node):
        """Calcula la matriu de costos entre predecessors i successors del node."""
        previous = slice(self.left[node], self.first[node])
        targets = np.arange(self.after[node], self.right[node])
        dt = self.frame[targets] - self.frame[node]
        velocity = (self.centers[targets] - self.centers[node]) / dt[:, None]
        scale = np.sqrt(self.scales[node] * self.scales[targets])
        p = self.config
        distance = p.distance_weight * np.hypot(*velocity.T) / scale
        size = p.scale_weight * np.abs(np.log(self.scales[targets] / self.scales[node]))
        # Si manca un ID, la traça no aporta evidència d’un canvi d’identitat.
        identity = p.id_change_cost * ((self.track[node] != self.track[targets]) &
                                       (self.track[node] != 0) & (self.track[targets] != 0))
        base = distance + size + identity + (dt - 1) * p.missing_frame_cost
        if node == 0:
            return targets, base[None, :]
        old_dt = self.frame[node] - self.frame[previous]
        incoming = (self.centers[node] - self.centers[previous]) / old_dt[:, None]
        delta = incoming[:, None, :] - velocity[None, :, :]
        change = p.velocity_weight * np.hypot(delta[..., 0], delta[..., 1]) / scale
        return targets, change + base

    def solve(self):
        """Calcula el camí mínim i el millor camí complet per cada caixa o buit."""
        count = len(self.nodes)
        forward = np.full((count, self.width), np.inf)
        parent = np.full(forward.shape, -1, dtype=np.int32)
        forward[0, 0] = 0.0
        for current in range(count):
            targets, costs = self.transitions(current)
            if not costs.size:
                continue
            prefix = forward[current, :costs.shape[0]]
            complete = prefix[:, None] + costs
            slots = complete.argmin(axis=0)
            offsets = current - self.left[targets]
            forward[targets, offsets] = complete[slots, np.arange(targets.size)]
            parent[targets, offsets] = slots

        terminal = forward.min(axis=1) + self.tail
        node = int(terminal.argmin())
        slot = int(forward[node].argmin())
        observations = {}
        while node != 0:
            observations[int(self.frame[node])] = self.nodes[node]
            node, slot = int(self.left[node] + slot), int(parent[node, slot])
        seed = self.nodes[0]
        observations[seed.frame] = seed

        # Un camí sense observació en un fotograma o bé hi salta per sobre o bé ha acabat abans.
        gap = np.full(self.frame_count + 1, np.inf)
        np.minimum.at(gap, self.frame + 1, terminal)
        gap = np.minimum.accumulate(gap)
        suffix = np.full_like(forward, np.inf)
        for current in range(count - 1, -1, -1):
            slots = max(1, int(self.first[current] - self.left[current]))
            suffix[current, :slots] = self.tail[current]
            targets, costs = self.transitions(current)
            if not costs.size:
                continue
            after = costs + suffix[targets, current - self.left[targets]]
            suffix[current, :slots] = np.minimum(suffix[current, :slots], after.min(axis=1))
            through = (forward[current, :slots, None] + after).min(axis=0)
            for target_frame in range(int(self.frame[current]) + 2, int(self.frame[targets[-1]]) + 1):
                target_costs = through[self.frame[targets] == target_frame]
                if target_costs.size:
                    inside_gap = slice(int(self.frame[current]) + 1, target_frame)
                    gap[inside_gap] = np.minimum(gap[inside_gap], target_costs.min())

        by_frame = {}
        for candidate, cost in zip(self.nodes, (forward + suffix).min(axis=1), strict=True):
            if np.isfinite(cost):
                by_frame.setdefault(candidate.frame, {})[candidate.candidate_id] = float(cost)
        return SubjectPath(float(terminal.min()), observations, by_frame,
                           {i: float(cost) for i, cost in enumerate(gap[:-1]) if np.isfinite(cost)})
