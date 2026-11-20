"""Evidència respecte del fons fix per ordenar i agrupar regions candidates."""

from dataclasses import dataclass, replace

import cv2
import numpy as np

from trampoline_vision.preparation.regions import Region, area, combine_sources, overlap


def validate_pixels(image, shape=None):
    """Valida píxels BGR uint8 originals i, si es declara, la geometria del vídeo."""
    if (not isinstance(image, np.ndarray) or image.dtype != np.uint8 or image.ndim != 3
            or image.shape[2] != 3 or min(image.shape[:2]) < 2
            or (shape is not None and image.shape != shape)):
        raise ValueError("Expected matching BGR uint8 video pixels")


def downsample(image):
    """Redueix a mitja resolució amb la interpolació d’àrea emprada al banc."""
    return cv2.resize(image, None, fx=.5, fy=.5, interpolation=cv2.INTER_AREA)


def sample_indices(stop: int, count: int = 21) -> tuple[int, ...]:
    """Mostreja uniformement l’interval disponible, incloent-ne els extrems."""
    if stop < 1 or count < 1:
        raise ValueError("Background needs a non-empty frame interval and sample budget")
    count = min(stop, count)
    return tuple(i * (stop - 1) // max(1, count - 1) for i in range(count))


def median_background(images):
    """Calcula el fons medià immutable i retorna la geometria BGR original."""
    shape = None
    small = []
    for image in images:
        validate_pixels(image, shape)
        shape = image.shape
        small.append(downsample(image))
    if not small:
        raise ValueError("Silhouette preparation requires background samples")
    background = np.median(np.stack(small), axis=0).astype(np.uint8)
    background.flags.writeable = False
    return background, shape


def foreground(image, background):
    """Etiqueta components de diferència, elimina soroll aïllat i tanca petits buits."""
    difference = cv2.absdiff(downsample(image), background).max(axis=2)
    mask = (difference >= 27).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), dtype=np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), dtype=np.uint8))
    _, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    sizes = stats[:, cv2.CC_STAT_AREA]
    keep = sizes >= 30
    keep[0] = False
    labels[~keep[labels]] = 0
    return labels, sizes


def component_evidence(box, labels, sizes):
    """Mesura el component dominant, la fracció de caixa ocupada i la cobertura del component."""
    height, width = labels.shape
    x0, y0 = np.maximum(0, np.floor(box[:2] * .5).astype(int))
    x1, y1 = np.minimum([width, height], np.ceil(box[2:] * .5).astype(int))
    roi = labels[y0:y1, x0:x1]
    if not roi.size:
        return 0, 0., 0., 0.
    counts = np.bincount(roi.ravel())
    counts[0] = 0
    if not counts.any():
        return 0, 0., 0., 0.
    component = int(np.argmax(counts))
    shared = counts[component]
    return component, shared / roi.size, shared / sizes[component], counts.sum() / roi.size


@dataclass(frozen=True)
class _RankedRegion:
    """Regió candidata amb puntuació d’ordre i evidència del component de primer pla."""

    region: Region
    value: float
    component: int
    component_coverage: float


def _in_zone(box, zone):
    """Accepta caixes amb el centre o almenys el 55% de l’àrea dins la zona."""
    center = (box[:2] + box[2:]) * .5
    return np.all((center >= zone[:2]) & (center <= zone[2:])) or overlap(box, zone) / area(box) >= .55


def _rank(region, labels, sizes, zone):
    """Puntua suport localitzat de silueta i extensió, amb preferències de confiança i posició."""
    box = np.asarray(region.bbox)
    component, fill, cover, all_fill = component_evidence(box, labels, sizes)
    confidence = region.region_score if region.region_score is not None else region.anchor_score
    priority = (.62 * np.sqrt(fill * cover) + .18 * all_fill + .16 * np.sqrt(confidence)
                + .04 * np.sqrt(overlap(box, zone) / area(box)))
    pixels = float(area(box)) * .25 * fill
    extent = np.sqrt(min(pixels / 480., 1.))
    half_width = (zone[2] - zone[0]) * .5
    center = 1. - min(abs((box[0] + box[2]) * .5 - (zone[0] + zone[2]) * .5) / half_width, 1.)
    return _RankedRegion(region, float(.66 * priority + .29 * extent + .05 * center), component, float(cover))


def _contains(keeper, other):
    """Accepta fragments compatibles quan la representant cobreix directament el 95% de la caixa."""
    a, b = np.asarray(keeper.region.bbox), np.asarray(other.region.bbox)
    a_area, b_area = area(a), area(b)
    shared = overlap(a, b)
    if shared / b_area < .95:
        return False
    near = shared / (a_area + b_area - shared) >= .67
    fragment = (other.component != 0 and other.component == keeper.component and b_area <= .80 * a_area
                and (other.region.anchor_score < .1 or other.component_coverage + .18 < keeper.component_coverage))
    return bool(near or fragment)


@dataclass(frozen=True)
class RegionDecision:
    """Decisió geomètrica interna, abans de resoldre els membres a fonts originals."""

    region: Region
    ranking_score: float | None
    reason: str
    selected_anchor_source_id: str | None


def rank_regions_with_audit(regions, image, background, zone, *, hard_zone, limit):
    """Retorna regions actives i una decisió per regió: selecció, fusió, zona o límit.

    La puntuació ordena regions; no representa probabilitat ni confiança YOLO.
    Una fusió aporta procedència a la representant sense expandir-ne la caixa.
    """
    labels, sizes = foreground(image, background)
    ranked, decisions = [], []
    for region in regions:
        if hard_zone and not _in_zone(np.asarray(region.bbox), zone):
            decisions.append(RegionDecision(region, None, "outside_hard_zone", None))
        else:
            ranked.append(_rank(region, labels, sizes, zone))
    ranked.sort(key=lambda entry: (-entry.value, entry.region.anchor))
    kept = []
    for entry in ranked:
        selected = None
        reason = "candidate_limit"
        for i, keeper in enumerate(kept):
            if _contains(keeper, entry):
                kept[i] = replace(keeper, region=combine_sources(keeper.region, entry.region))
                selected = keeper.region.anchor_source_id
                reason = "absorbed_containment"
                break
        else:
            # Amb el límit assolit, encara es pot aportar procedència als grups actius.
            if len(kept) < limit:
                kept.append(entry)
                selected = entry.region.anchor_source_id
                reason = "selected"
        decisions.append(RegionDecision(entry.region, entry.value, reason, selected))
    return tuple(entry.region for entry in kept), tuple(decisions)


def rank_regions(regions, image, background, zone, *, hard_zone, limit):
    """Manté l’entrada simple per a consumidors que només necessiten les regions actives."""
    return rank_regions_with_audit(regions, image, background, zone, hard_zone=hard_zone, limit=limit)[0]
