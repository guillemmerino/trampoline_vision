"""Exportació auditable de preparació, sense executar ni serialitzar un tracker.

El registre és autosuficient per recuperar caixes, scores i procedència de
totes les fonts. La política efectiva acompanya la interpretació preparada;
la font completa continua separada dels representants i relacions.
"""

from dataclasses import asdict

from trampoline_vision.contracts.tracking import TrackingFrame
from trampoline_vision.preparation.config import PreparationConfig
from trampoline_vision.preparation.audit import RepresentativePreparationResult


def preparation_record(frame: TrackingFrame, config: PreparationConfig,
                       *, audit: RepresentativePreparationResult | None = None) -> dict:
    """Serialitza font intacta, candidats, relacions i política, sense perdre alternatives.

    El caller ha de passar la mateixa configuració usada per preparar el
    fotograma. No genera IDs temporals, observacions articulars ni prediccions.
    """
    if not isinstance(frame, TrackingFrame) or not isinstance(config, PreparationConfig):
        raise ValueError("preparation_record requires TrackingFrame and PreparationConfig")
    if audit is not None and (not isinstance(audit, RepresentativePreparationResult) or audit.frame is not frame):
        raise ValueError("Preparation audit must belong to the supplied frame")
    record = {"schema_version": "1.0", "task": "prepare_detections",
            "source": asdict(frame.source), "candidates": [asdict(c) for c in frame.candidates],
            "relations": [asdict(r) for r in frame.relations],
            "effective_config": {"schema_version": "1.0", **asdict(config)}}
    if audit is not None:
        record["selection_audit"] = {
            "source_count": audit.source_count, "grouped_count": audit.grouped_count,
            "region_count": audit.region_count, "selected_count": len(frame.candidates),
            "selections": [asdict(selection) for selection in audit.selections],
        }
    return record
