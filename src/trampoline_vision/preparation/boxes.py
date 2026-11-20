"""Preparació espacial de deteccions de persona: representants, fonts i contencions.

Tot és pur i d'un sol fotograma, amb biblioteca estàndard. No hi ha inferència,
historial, selector del gimnasta, IDs temporals ni reconstrucció d'esquelets.
Les caixes i confiances són observades: no es fan mitjanes, unions ni padding.
"""

from dataclasses import replace

from trampoline_vision.contracts.observations import FrameDetections, PersonBoxDetection
from trampoline_vision.contracts.tracking import BoxMeasurement, BoxRelation, TrackingCandidate, TrackingFrame
from trampoline_vision.preparation.config import BoxPreparationPolicy


def _area(box):
    """Retorna l'àrea contínua d'un BoundingBox ja validat, sense sumar píxels."""
    return (box.x_max - box.x_min) * (box.y_max - box.y_min)


def _intersection(a, b):
    """Calcula l'àrea comuna; les caixes disjuntes o que només es toquen donen zero."""
    return max(0.0, min(a.x_max, b.x_max) - max(a.x_min, b.x_min)) * max(
        0.0, min(a.y_max, b.y_max) - max(a.y_min, b.y_min))


def _similar_geometry(a, b, policy):
    """Exigeix semblança de mida, centre i IoU sense imposar una postura vertical."""
    aa, ab = _area(a), _area(b)
    wa, wb = a.x_max - a.x_min, b.x_max - b.x_min
    ha, hb = a.y_max - a.y_min, b.y_max - b.y_min
    if (min(wa, wb) < policy.min_size_similarity * max(wa, wb)
            or min(ha, hb) < policy.min_size_similarity * max(ha, hb)
            or abs(a.x_min + a.x_max - b.x_min - b.x_max) > 2 * policy.max_center_distance_ratio * min(wa, wb)
            or abs(a.y_min + a.y_max - b.y_min - b.y_max) > 2 * policy.max_center_distance_ratio * min(ha, hb)):
        return False
    intersection = _intersection(a, b)
    return intersection / (aa + ab - intersection) > policy.min_duplicate_iou


def select_representative(group: tuple[PersonBoxDetection, ...]) -> PersonBoxDetection:
    """Prefereix la caixa observada de més àrea entre duplicats de geometria semblant.

    Això prioritza cobertura aproximada. Empata per confiança i ID estable;
    la confiança retornada continua sent la d'aquesta detecció, sense inflar-la.
    No s'aplica a totes les contencions: podrien ser dues persones diferents.
    """
    if not group:
        raise ValueError("Cannot select a representative from an empty group")
    return min(group, key=lambda d: (-_area(d.bbox), -d.score, d.detection_id))


def group_boxes(boxes: tuple[PersonBoxDetection, ...], policy: BoxPreparationPolicy) -> tuple[tuple[PersonBoxDetection, ...], ...]:
    """Agrupa alternatives febles compatibles amb TOTS els membres, sense unions en cadena.

    L'ancoratge és la detecció més confiada encara lliure. Cada font pertany
    exactament a un grup; la política desactivada preserva l'ordre d'entrada.
    El primer membre retornat és sempre el representant de cobertura.
    """
    if not isinstance(boxes, tuple) or any(not isinstance(d, PersonBoxDetection) for d in boxes):
        raise ValueError("group_boxes requires a tuple of PersonBoxDetection")
    if not isinstance(policy, BoxPreparationPolicy):
        raise ValueError("group_boxes requires BoxPreparationPolicy")
    if len({d.detection_id for d in boxes}) != len(boxes):
        raise ValueError("Duplicate source detection IDs")
    if not policy.enabled:
        return tuple((d,) for d in boxes)
    remaining = sorted(boxes, key=lambda d: (-d.score, d.detection_id))
    groups = []
    while remaining:
        anchor, *pending = remaining
        members, remaining = [anchor], []
        for alternative in pending:
            if (alternative.score <= policy.max_alternative_score_ratio * anchor.score
                    and all(_similar_geometry(alternative.bbox, member.bbox, policy) for member in members)):
                proposed = (*members, alternative)
                representative = select_representative(proposed)
                # Més àrea no garanteix més cobertura: una caixa més ampla
                # pot retallar els peus. Comprovar totes les fonts, sense GT.
                if all(_intersection(representative.bbox, d.bbox) >= policy.min_representative_coverage * _area(d.bbox)
                       for d in proposed):
                    members.append(alternative)
                else:
                    remaining.append(alternative)
            else:
                remaining.append(alternative)
        representative = select_representative(tuple(members))
        groups.append((representative, *sorted((d for d in members if d is not representative), key=lambda d: d.detection_id)))
    return tuple(sorted(groups, key=lambda g: g[0].detection_id))


def find_box_relations(candidates: tuple[TrackingCandidate, ...], policy: BoxPreparationPolicy) -> tuple[BoxRelation, ...]:
    """Relaciona contencions de mesures observades sense agrupar-les ni triar un actor.

    Una caixa petita pot tenir diversos contenidors. La confiança no resol
    aquesta ambigüitat i no s'utilitza per eliminar candidats. Cost O(n²),
    amb rebuig ràpid per àrea i separació abans de calcular el solapament.
    """
    if not policy.enabled:
        return ()
    measured = sorted((c for c in candidates if c.measurement is not None), key=lambda c: c.candidate_id)
    relations = []
    for i, first in enumerate(measured):
        for second in measured[i + 1:]:
            a, b = first.measurement.bbox, second.measurement.bbox
            aa, ab = _area(a), _area(b)
            if aa == ab:
                continue
            small, large = (first, second) if aa < ab else (second, first)
            area_small, area_large = min(aa, ab), max(aa, ab)
            ratio = area_small / area_large
            if not policy.min_contained_area_ratio <= ratio <= policy.max_contained_area_ratio:
                continue
            intersection = _intersection(a, b)
            if intersection > 0 and intersection / area_small >= policy.min_containment_ios:
                relations.append(BoxRelation(small.candidate_id, large.candidate_id,
                                             intersection / (aa + ab - intersection), intersection / area_small, ratio))
    return tuple(sorted(relations, key=lambda r: (r.smaller_candidate_id, r.larger_candidate_id)))


def prepare_boxes(source: FrameDetections, policy: BoxPreparationPolicy = BoxPreparationPolicy(), *,
                  include_relations: bool = True) -> TrackingFrame:
    """Produeix candidats i relacions mantenint la font original i una partició completa.

    Els IDs històrics de caixa es mantenen quan els índexs externs són únics;
    si una font personalitzada els repeteix, s'usen IDs de detecció inequívocs.
    Els avisos expressen geometria potencial, no diagnòstics anatòmics.
    include_relations=False permet reutilitzar el mateix agrupament i les
    mateixes fonts sense calcular relacions que un altre model no consumeix.
    """
    if not isinstance(source, FrameDetections):
        raise ValueError("prepare_boxes requires FrameDetections")
    groups = group_boxes(source.detections, policy)
    unique_indices = len({d.provenance.source_person_index for d in source.detections}) == len(source.detections)
    candidates = []
    for group in groups:
        representative = group[0]
        suffix = representative.provenance.source_person_index if unique_indices else representative.detection_id
        issues = ("pose_not_available",) + (("box_duplicates_grouped",) if len(group) > 1 else ())
        if representative.score < max(d.score for d in group):
            issues += ("representative_has_lower_confidence",)
        candidates.append(TrackingCandidate(
            f"{source.context.frame_index}:box_candidate:{suffix}", tuple(d.detection_id for d in group),
            BoxMeasurement(representative.bbox, "detector", representative.score, "recorded_detector_confidence"), issues))
    relations = find_box_relations(tuple(candidates), policy) if include_relations else ()
    smaller = {r.smaller_candidate_id for r in relations}
    larger = {r.larger_candidate_id for r in relations}
    related = smaller | larger
    candidates = tuple(replace(c, issues=c.issues + (("ambiguous_containment",) if c.candidate_id in related else ())
                               + (("possible_partial",) if c.candidate_id in smaller else ())
                               + (("contains_other_candidates",) if c.candidate_id in larger else ())) for c in candidates)
    # No omissió silenciosa: el contracte general admet fonts sense candidat,
    # però aquest preparador de caixes garanteix que totes estan representades.
    refs = [ref for c in candidates for ref in c.source_detection_ids]
    if len(refs) != len(source.detections) or set(refs) != {d.detection_id for d in source.detections}:
        raise ValueError("Box preparation must reference every original detection exactly once")
    return TrackingFrame(source, candidates, relations)
