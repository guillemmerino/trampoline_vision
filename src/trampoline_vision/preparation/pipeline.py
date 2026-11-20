"""Entrada pública de preparació de candidats, reutilitzable per aplicació, proves i futur worker.

Les funcions són pures i treballen sobre els contractes canònics. No llegeixen
vídeos, no executen inferència ni OC-SORT i no publiquen artefactes.
"""

from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING

from trampoline_vision.contracts.observations import FrameDetections, PersonBoxDetection
from trampoline_vision.contracts.tracking import TrackingCandidate, TrackingFrame
from trampoline_vision.preparation.boxes import prepare_boxes
from trampoline_vision.preparation.config import PreparationConfig
from trampoline_vision.preparation.deduplication import group_poses
from trampoline_vision.preparation.pose import prepare_pose


if TYPE_CHECKING:
    from trampoline_vision.preparation.representative import RepresentativeBoxPreparer


def prepare_frame(source: FrameDetections, config: PreparationConfig = PreparationConfig(), *,
                  representative: "RepresentativeBoxPreparer | None" = None, image=None) -> TrackingFrame:
    """Converteix totes les deteccions en candidats, agrupant només duplicats compatibles.

    Els perfils conservadors referencien cada detecció original exactament
    una vegada. El primer source_detection_id identifica el representant
    o la llavor que aporta el score; els altres són suport del mateix grup.
    Els IDs de candidats són locals al fotograma i no són identitats temporals.
    El perfil representatiu requereix un preparador ajustat al vídeo i píxels
    BGR. Manté les deteccions al source, encara que en limiti les candidates.
    """
    if not isinstance(source, FrameDetections) or not isinstance(config, PreparationConfig):
        raise ValueError("prepare_frame requires FrameDetections and PreparationConfig")
    if config.representative_boxes is not None:
        if representative is None or representative.config != config or image is None:
            raise ValueError("Representative preparation requires a matching fitted preparer and frame pixels")
        return representative.prepare(source, image)
    if representative is not None or image is not None:
        raise ValueError("Frame pixels require an explicit representative box profile")
    boxes = tuple(d for d in source.detections if isinstance(d, PersonBoxDetection))
    if boxes:
        if len(boxes) != len(source.detections):
            raise ValueError("Box and pose sources must be associated explicitly, not mixed by preparation")
        return prepare_boxes(source, config.box_preparation)
    poses = tuple(prepare_pose(d, source.context, config.box) for d in source.detections)
    candidates = []
    for group in group_poses(poses, config.deduplication):
        representative = group[0]
        refs = (representative.detection.detection_id,) + tuple(sorted(p.detection.detection_id for p in group[1:]))
        # Les limitacions de totes les fonts es conserven; no són articulacions fusionades.
        issues = tuple(dict.fromkeys(issue for pose in group for issue in pose.issues))
        if len(group) > 1:
            issues += ("duplicates_grouped",)
        candidates.append(TrackingCandidate(
            candidate_id=f"{source.context.frame_index}:candidate:{refs[0]}",
            source_detection_ids=refs,
            measurement=representative.measurement,
            issues=issues,
        ))
    return TrackingFrame(source, tuple(candidates))


def prepare_frames(frames: Iterable[FrameDetections], config: PreparationConfig = PreparationConfig(), *,
                   representative: "RepresentativeBoxPreparer | None" = None,
                   images: Iterable | None = None) -> Iterator[TrackingFrame]:
    """Transforma un stream de manera mandrosa, preservant també fotogrames buits o sense JSON.

    No emmagatzema el vídeo complet ni imposa una freqüència temporal. Validar
    continuïtat i ordre entre instants correspondrà al futur servei de tracking.
    """
    if images is None:
        for frame in frames:
            yield prepare_frame(frame, config, representative=representative)
    else:
        for frame, image in zip(frames, images, strict=True):
            yield prepare_frame(frame, config, representative=representative, image=image)
