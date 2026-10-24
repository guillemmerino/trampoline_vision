"""Entrada pública de preparació de candidats, reutilitzable per aplicació, proves i futur worker.

Les funcions són pures i treballen sobre els contractes canònics. No llegeixen
vídeos, no executen inferència ni OC-SORT i no publiquen artefactes.
"""

from collections.abc import Iterable, Iterator

from trampoline_vision.contracts.observations import FrameDetections
from trampoline_vision.contracts.tracking import TrackingCandidate, TrackingFrame
from trampoline_vision.preparation.config import PreparationConfig
from trampoline_vision.preparation.deduplication import group_poses
from trampoline_vision.preparation.pose import prepare_pose


def prepare_frame(source: FrameDetections, config: PreparationConfig = PreparationConfig()) -> TrackingFrame:
    """Converteix totes les deteccions en candidats, agrupant només duplicats compatibles.

    Cada detecció original queda referenciada exactament una vegada. El primer
    source_detection_id és el representant que aporta la mesura; la resta són
    duplicats agrupats, sense alterar-ne les observacions ni incrementar el score.
    Els IDs de candidats són locals al fotograma i no són identitats temporals.
    """
    if not isinstance(source, FrameDetections) or not isinstance(config, PreparationConfig):
        raise ValueError("prepare_frame requires FrameDetections and PreparationConfig")
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


def prepare_frames(frames: Iterable[FrameDetections], config: PreparationConfig = PreparationConfig()) -> Iterator[TrackingFrame]:
    """Transforma un stream de manera mandrosa, preservant també fotogrames buits o sense JSON.

    No emmagatzema el vídeo complet ni imposa una freqüència temporal. Validar
    continuïtat i ordre entre instants correspondrà al futur servei de tracking.
    """
    for frame in frames:
        yield prepare_frame(frame, config)
