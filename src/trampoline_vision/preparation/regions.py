"""Agrupament espacial de les candidates abans del rànquing per silueta.

Cada candidata referencia les deteccions originals que la formen.
La proposta conserva aquesta procedència quan la caixa prové d’un altre
membre del grup o de l’extensió d’un veïnat de deteccions febles.
"""

from dataclasses import dataclass, replace

import numpy as np

from trampoline_vision.contracts.tracking import TrackingFrame


def area(box):
    """Calcula l’àrea contínua d’una caixa xyxy o d’un conjunt de caixes."""
    return np.prod(box[..., 2:] - box[..., :2], axis=-1)


def overlap(first, second):
    """Calcula interseccions entre caixes aprofitant la difusió de dimensions de NumPy."""
    shared = np.minimum(first[..., 2:], second[..., 2:]) - np.maximum(first[..., :2], second[..., :2])
    return np.prod(np.maximum(0, shared), axis=-1)


def xyxy(box):
    """Llegeix les coordenades xyxy de la caixa del domini."""
    return (box.x_min, box.y_min, box.x_max, box.y_max)


@dataclass(frozen=True)
class Region:
    """Hipòtesi espacial amb els índexs dels grups conservadors S0 que explica."""

    anchor: int
    anchor_source_id: str
    anchor_score: float
    members: tuple[int, ...]
    bbox: tuple[float, float, float, float]
    observed_region: int | None  # None indica una extensió espacial derivada del suport.
    region_score: float | None  # Confiança del rectangle observat, quan existeix.


@dataclass(frozen=True)
class _Geometry:
    """Matrius geomètriques de fonts i parelles de candidates reutilitzables dins un fotograma."""

    boxes: np.ndarray
    areas: np.ndarray
    overlaps: np.ndarray
    iou: np.ndarray
    scores: np.ndarray
    ids: tuple[str, ...]
    members: tuple[np.ndarray, ...]
    representatives: np.ndarray
    seeds: np.ndarray
    covers: np.ndarray
    neighbours: np.ndarray
    weights: np.ndarray
    area_limit: float

    @classmethod
    def from_frame(cls, frame):
        """Calcula la cobertura directa de totes les fonts i un suport per candidata S0."""
        raw = frame.source.detections
        boxes = np.asarray([xyxy(d.bbox) for d in raw], dtype=float).reshape(-1, 4)
        areas = area(boxes)
        shared = overlap(boxes[:, None, :], boxes[None, :, :])
        iou = shared / (areas[:, None] + areas[None, :] - shared)
        scores = np.asarray([d.score for d in raw])
        ids = tuple(d.detection_id for d in raw)
        indices = {source_id: i for i, source_id in enumerate(ids)}
        members = tuple(np.array([indices[ref] for ref in c.source_detection_ids], dtype=int)
                        for c in frame.candidates)
        reps = np.array([group[0] for group in members], dtype=int)
        seeds = np.array([min(group, key=lambda i: (-scores[i], ids[i])) for group in members], dtype=int)
        covers = np.empty((len(reps), len(reps)), dtype=bool)
        for j, sources in enumerate(members):
            covers[:, j] = np.all(shared[reps[:, None], sources] / areas[sources] >= .95, axis=1)
        seed_areas = areas[seeds]
        ios = shared[seeds[:, None], seeds[None, :]] / np.minimum(seed_areas[:, None], seed_areas)
        ratios = seed_areas[None, :] / seed_areas[:, None]
        neighbours = (ios >= .5) & (ratios >= .1) & (ratios <= 10.)
        np.fill_diagonal(neighbours, False)
        context = frame.source.context
        return cls(boxes, areas, shared, iou, scores, ids, members, reps, seeds, covers,
                   neighbours, np.sqrt(scores[seeds]), .10 * (context.width_px * context.height_px))

    def proposal(self, anchor, members, box, observed_region=None):
        """Conserva la confiança observada i explicita la llavor quan l’extensió és derivada."""
        seed = self.seeds[anchor]
        score = None if observed_region is None else float(self.scores[self.representatives[observed_region]])
        return Region(anchor, self.ids[seed], float(self.scores[seed]), tuple(members),
                      tuple(float(x) for x in box), observed_region, score)


def _strong_neighbours(geometry, strong, weak, seed_scores):
    """Assigna veïnes febles per encaix i reserva les ambigües per a la fase regional."""
    attached = {i: [] for i in strong}
    free = set(weak)
    for candidate in weak:
        fits = []
        rep = geometry.representatives[candidate]
        for anchor in strong:
            if not geometry.neighbours[anchor, candidate]:
                continue
            seed = geometry.seeds[anchor]
            shared = geometry.overlaps[seed, rep]
            fit = (geometry.iou[seed, rep] + .5 * shared / geometry.areas[rep]
                   + .1 * shared / geometry.areas[seed])
            fits.append((float(fit), anchor))
        fits.sort(key=lambda item: (-item[0], -seed_scores[item[1]], item[1]))
        if fits and (len(fits) == 1 or fits[0][0] - fits[1][0] >= .1):
            attached[fits[0][1]].append(candidate)
            free.remove(candidate)
    return attached, free


def _strengthened_region(geometry, anchor, neighbours, strong, seed_scores):
    """Valora una caixa observada més ampla si el suport addicional compensa el creixement."""
    reps, boxes = geometry.representatives, geometry.boxes
    initial = boxes[reps[anchor]]
    initial_area = float(area(initial))
    anchor_area = geometry.areas[geometry.seeds[anchor]]
    cap = 1.5 if seed_scores[anchor] >= .5 else 3.
    max_area = max(initial_area, cap * anchor_area)
    other_seeds = geometry.seeds[[j for j in strong if j != anchor]]
    other_boxes = boxes[other_seeds]
    initial_coverage = overlap(initial, other_boxes) / geometry.areas[other_seeds]
    best_region, best_gain = anchor, 0.
    for trial in neighbours:
        box = boxes[reps[trial]]
        new_area = float(area(box))
        if not initial_area <= new_area <= min(max_area, geometry.area_limit):
            continue
        if not geometry.covers[trial, anchor]:
            continue
        new_coverage = overlap(box, other_boxes) / geometry.areas[other_seeds]
        if np.any((new_coverage >= .5) & (initial_coverage < .5)):
            continue
        extra = [j for j in neighbours if j != trial and geometry.covers[trial, j]
                 and not geometry.covers[anchor, j]]
        gain = float(geometry.weights[extra].sum()) - .1 * np.log(new_area / initial_area)
        if gain > best_gain + 1e-12:
            best_region, best_gain = trial, gain
    retained = [j for j in neighbours if geometry.covers[best_region, j]]
    unexplained = set(neighbours) - set(retained)
    return geometry.proposal(anchor, (anchor, *retained), boxes[reps[best_region]], best_region), unexplained


def _weak_regions(geometry, free, seed_scores):
    """Agrupa veïnats febles d’una llavor en extensions limitades i conserva les aïllades."""
    boxes, reps = geometry.boxes, geometry.representatives
    blocked = set()
    while True:
        choices = []
        for seed in free - blocked:
            neighbours = [j for j in free if j != seed and geometry.neighbours[seed, j]]
            if len(neighbours) >= 3:
                choices.append((len(neighbours), float(seed_scores[seed]), seed, neighbours))
        if not choices:
            break
        _, _, seed, neighbours = max(choices, key=lambda item: (item[0], item[1], -item[2]))
        box = boxes[reps[seed]].copy()
        limit = min(6. * float(area(box)), geometry.area_limit)
        members = [seed]
        for j in sorted(neighbours, key=lambda j: (-geometry.iou[reps[seed], reps[j]], -seed_scores[j], j)):
            other = boxes[reps[j]]
            merged = np.r_[np.minimum(box[:2], other[:2]), np.maximum(box[2:], other[2:])]
            if area(merged) <= limit:
                box = merged
                members.append(j)
        if len(members) < 4:
            blocked.add(seed)
            continue
        free.difference_update(members)
        yield geometry.proposal(seed, members, box)
    for j in sorted(free):
        yield geometry.proposal(j, (j,), boxes[reps[j]], j)


def group_regions(frame: TrackingFrame) -> tuple[Region, ...]:
    """Protegeix les àncores fortes i agrupa espacialment el suport feble restant."""
    if not frame.candidates:
        return ()
    geometry = _Geometry.from_frame(frame)
    scores = geometry.scores[geometry.seeds]
    strong = np.flatnonzero(scores >= .1).tolist()
    weak = np.flatnonzero(scores < .1).tolist()
    attached, free = _strong_neighbours(geometry, strong, weak, scores)
    groups = []
    for anchor in strong:
        region, unexplained = _strengthened_region(geometry, anchor, attached[anchor], strong, scores)
        groups.append(region)
        free.update(unexplained)
    return (*groups, *_weak_regions(geometry, free, scores))


def combine_sources(keeper: Region, absorbed: Region) -> Region:
    """Conserva la geometria de més prioritat i combina la procedència dels dos grups."""
    return replace(keeper, members=(*keeper.members, *absorbed.members))
