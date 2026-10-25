"""Fixtures de caixes independents de poses per als adaptadors i el cache."""

from trampoline_vision.contracts.geometry import BoundingBox
from trampoline_vision.contracts.observations import DetectionProvenance, FrameContext, FrameDetections, PersonBoxDetection
from trampoline_vision.contracts.appearance import CandidateEmbedding, FrameAppearance
from trampoline_vision.preparation.pipeline import prepare_frame


def box_frame(index=0, people=(0, 1), score=.9):
    """Genera persones separades que poden canviar d'ordre sense canviar de geometria."""
    detections = tuple(PersonBoxDetection(f'{index}:box:{person}', BoundingBox(5 + person*30, 5, 20 + person*30, 45), score,
        DetectionProvenance('synthetic.csv', f'csv_line:{person+2}', index, person, 'synthetic', 'original')) for person in people)
    return prepare_frame(FrameDetections(FrameContext('boxes', index, index/30, 1/30, 96, 64), detections, 'present'))


def appearance(frame, fingerprint='synthetic-osnet'):
    """Vectors ortogonals normalitzats: permeten provar ReID sense entrenar ni carregar pesos."""
    return FrameAppearance(frame.source.context, fingerprint, tuple(CandidateEmbedding(candidate.candidate_id,
        tuple(1. if i == int(candidate.source_detection_ids[0].split(':')[-1]) else 0. for i in range(512)))
        for candidate in frame.candidates))
