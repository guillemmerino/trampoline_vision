"""Derivació explícita de caixes de pose i evidència usada per comparar candidats.

Només s'utilitzen punts observats dins de la imatge. No s'extrapolen membres,
no es fa servir cap model temporal i no s'estima una caixa de cos complet.
El mapa anatòmic és BODY_25; un nou esquema necessitarà un adaptador explícit.
"""

from dataclasses import dataclass
import math

from trampoline_vision.contracts.observations import FrameContext, KeypointObservation, PersonDetection
from trampoline_vision.contracts.tracking import BoundingBox, BoxMeasurement
from trampoline_vision.preparation.config import PoseBoxPolicy


_GROUPS = {
    "nose": "head", "right_eye": "head", "left_eye": "head",
    "right_ear": "head", "left_ear": "head",
    "neck": "core", "mid_hip": "core", "right_shoulder": "core",
    "left_shoulder": "core", "right_hip": "core", "left_hip": "core",
    "right_elbow": "arms", "left_elbow": "arms", "right_wrist": "arms", "left_wrist": "arms",
    "right_knee": "legs", "left_knee": "legs", "right_ankle": "legs", "left_ankle": "legs",
    "right_big_toe": "legs", "left_big_toe": "legs", "right_small_toe": "legs",
    "left_small_toe": "legs", "right_heel": "legs", "left_heel": "legs",
}  # Agrupació de suport, no reconstrucció anatòmica ni simetria esquerra/dreta.


@dataclass(frozen=True)
class PreparedPose:
    """Evidència intermèdia d'una detecció; permet deduplicar sense rellegir ni alterar punts."""

    detection: PersonDetection  # Instància original, amb tota la procedència intacta.
    points: tuple[KeypointObservation, ...]  # Punts seleccionats per la política de preparació.
    extent: BoundingBox | None  # Extensió abans de padding; només si el suport és suficient.
    measurement: BoxMeasurement | None  # Caixa ampliada i indicador, o absència explícita.
    issues: tuple[str, ...]  # Causes de manca de caixa i limitacions de la mesura.


def prepare_pose(detection: PersonDetection, context: FrameContext, policy: PoseBoxPolicy) -> PreparedPose:
    """Calcula extensió i confiança mitjana dels punts seleccionats d'una sola detecció.

    Un punt necessita valid=True, in_frame=True i confiança positiva >= llindar.
    Les comprovacions de suport precedeixen el padding, que no pot rescatar una
    pose col·lapsada. La mitjana és un indicador descriptiu, no calibrat.
    """
    if detection.skeleton_schema != "openpose_body25":
        raise ValueError("Pose preparation only supports openpose_body25")
    points = tuple(p for p in detection.keypoints if p.valid and p.in_frame
                   and p.confidence > 0 and p.confidence >= policy.min_keypoint_confidence)
    issues: list[str] = []
    if any(p.valid and not p.in_frame for p in detection.keypoints):
        issues.append("points_outside_frame")
    if any(p.valid and p.in_frame and p.confidence < policy.min_keypoint_confidence for p in detection.keypoints):
        issues.append("points_below_preparation_threshold")
    if len(points) < policy.min_points:
        issues.append("insufficient_points")
    groups = {_GROUPS[p.name] for p in points}
    if len(groups) < policy.min_anatomical_groups or (policy.require_core and "core" not in groups):
        issues.append("insufficient_anatomical_support")

    minimum = max(policy.min_span_px, policy.min_span_image_ratio * math.hypot(context.width_px, context.height_px))
    if points:
        x0, x1 = min(p.x for p in points), max(p.x for p in points)
        y0, y1 = min(p.y for p in points), max(p.y for p in points)
        width, height = x1 - x0, y1 - y0
    else:
        x0 = y0 = x1 = y1 = width = height = 0.0
    if width <= 0 or height <= 0 or width < minimum or height < minimum:
        issues.append("insufficient_spatial_support")
    failures = {"insufficient_points", "insufficient_anatomical_support", "insufficient_spatial_support"}
    if failures.intersection(issues):
        return PreparedPose(detection, points, None, None, tuple(issues))

    extent = BoundingBox(x0, y0, x1, y1)
    dx, dy = width * policy.padding_ratio, height * policy.padding_ratio
    bbox = BoundingBox(x0 - dx, y0 - dy, x1 + dx, y1 + dy)
    score = math.fsum(p.confidence / len(points) for p in points)
    measurement = BoxMeasurement(bbox, "pose_extent", score, "selected_keypoint_confidence_mean_v1")
    issues.append("pose_extent_only")
    return PreparedPose(detection, points, extent, measurement, tuple(issues))
