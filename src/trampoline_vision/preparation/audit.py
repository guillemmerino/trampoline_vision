"""Contractes immutables d’auditoria de selecció, independents del tracker i dels píxels."""

from dataclasses import dataclass

from trampoline_vision.contracts.tracking import TrackingFrame


@dataclass(frozen=True)
class CandidateSelection:
    """Explica el destí d’una regió i identifica totes les deteccions que l’han originat.

    ranking_score és una puntuació d’ordre, no confiança del detector. Una regió
    absorbida apunta a l’àncora seleccionada; zona i límit no tenen destinatària.
    """

    anchor_source_id: str
    source_detection_ids: tuple[str, ...]
    bbox_xyxy: tuple[float, float, float, float]
    ranking_score: float | None
    reason: str
    selected_anchor_source_id: str | None


@dataclass(frozen=True)
class RepresentativePreparationResult:
    """Ajunta la sortida preparada i les decisions prèvies al tall per poder-les revisar.

    source_count compta originals; grouped_count, grups S0; region_count, regions
    abans del rànquing. Les fonts íntegres són a frame.source, incloses les excloses.
    """

    frame: TrackingFrame
    source_count: int
    grouped_count: int
    region_count: int
    selections: tuple[CandidateSelection, ...]
