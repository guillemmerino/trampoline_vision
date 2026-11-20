"""Exportació auditable de preparació, sense executar ni serialitzar un tracker.

El registre és autosuficient per recuperar caixes, scores i procedència de
totes les fonts. La política efectiva acompanya la interpretació preparada;
la font completa continua separada dels representants i relacions.
"""

from dataclasses import asdict

from trampoline_vision.contracts.tracking import TrackingFrame
from trampoline_vision.preparation.config import PreparationConfig


def preparation_record(frame: TrackingFrame, config: PreparationConfig) -> dict:
    """Serialitza font intacta, candidats, relacions i política, sense perdre alternatives.

    El caller ha de passar la mateixa configuració usada per preparar el
    fotograma. No genera IDs temporals, observacions articulars ni prediccions.
    """
    if not isinstance(frame, TrackingFrame) or not isinstance(config, PreparationConfig):
        raise ValueError("preparation_record requires TrackingFrame and PreparationConfig")
    return {"schema_version": "1.0", "task": "prepare_detections",
            "source": asdict(frame.source), "candidates": [asdict(c) for c in frame.candidates],
            "relations": [asdict(r) for r in frame.relations],
            "effective_config": {"schema_version": "1.0", **asdict(config)}}
