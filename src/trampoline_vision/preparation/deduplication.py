"""Agrupació espacial conservadora de propostes d'un únic fotograma.

No és tracking: no hi ha història, identitats ni recuperació temporal. Calen
caixes solapades i articulacions homòlogues pròximes. Cada grup exigeix
compatibilitat entre totes les seves parelles per impedir unions per cadena.
"""

import math

from trampoline_vision.contracts.tracking import BoundingBox
from trampoline_vision.preparation.config import DeduplicationPolicy
from trampoline_vision.preparation.pose import PreparedPose


def box_iou(a: BoundingBox, b: BoundingBox) -> float:
    """Calcula intersecció/unió de caixes xyxy contínues, sense el +1 dels rectangles discrets."""
    width = max(0.0, min(a.x_max, b.x_max) - max(a.x_min, b.x_min))
    height = max(0.0, min(a.y_max, b.y_max) - max(a.y_min, b.y_min))
    intersection = width * height
    area_a = (a.x_max - a.x_min) * (a.y_max - a.y_min)
    area_b = (b.x_max - b.x_min) * (b.y_max - b.y_min)
    return intersection / (area_a + area_b - intersection)


def compatible_poses(a: PreparedPose, b: PreparedPose, policy: DeduplicationPolicy) -> bool:
    """Accepta duplicats només si tots els punts compartits respecten la tolerància d'escala.

    Les poses sense mesura suficient es mantenen separades. Es compara la
    menor diagonal per no deixar que una proposta enorme absorbeixi una de
    petita. No es corregeixen etiquetes esquerra/dreta ni es dedueix la rotació.
    """
    if a.extent is None or b.extent is None or box_iou(a.extent, b.extent) < policy.min_box_iou:
        return False
    a_points = {p.name: p for p in a.points}
    b_points = {p.name: p for p in b.points}
    shared = a_points.keys() & b_points.keys()
    if len(shared) < policy.min_shared_points:
        return False
    diagonal_a = math.hypot(a.extent.x_max - a.extent.x_min, a.extent.y_max - a.extent.y_min)
    diagonal_b = math.hypot(b.extent.x_max - b.extent.x_min, b.extent.y_max - b.extent.y_min)
    tolerance = policy.max_point_distance_ratio * min(diagonal_a, diagonal_b)
    return all(math.hypot(a_points[n].x - b_points[n].x, a_points[n].y - b_points[n].y) <= tolerance
               for n in shared)


def group_poses(poses: tuple[PreparedPose, ...], policy: DeduplicationPolicy) -> tuple[tuple[PreparedPose, ...], ...]:
    """Agrupa amb representant estable: més punts, més confiança i ID lexical per desempatar.

    La primera pose del grup és el representant. No es fa mitjana de caixes,
    ni suma de confiança, ni fusió d'articulacions. L'ordre d'entrada no
    modifica els grups si es mantenen els IDs i les dades de les deteccions.
    """
    ordered = sorted(poses, key=lambda p: (-len(p.points), -(p.measurement.score if p.measurement else 0),
                                         p.detection.detection_id))
    groups: list[list[PreparedPose]] = []
    for pose in ordered:
        if policy.enabled:
            for group in groups:
                if all(compatible_poses(pose, member, policy) for member in group):
                    group.append(pose)
                    break
            else:
                groups.append([pose])
        else:
            groups.append([pose])
    return tuple(tuple(group) for group in sorted(groups, key=lambda g: g[0].detection.detection_id))
