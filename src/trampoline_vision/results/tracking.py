"""Exportació compacta i dibuix del tracking sobre contractes propis.

Les caixes observades i les poses provenen de la mesura representant. Les
estimacions es dibuixen amb caixa discontínua i sense articulacions inventades.
"""

from dataclasses import asdict, dataclass
import hashlib

from trampoline_vision.contracts.tracking import TrackingFrameResult
from trampoline_vision.results.overlay import BODY25_EDGES, HEADER_HEIGHT, PALETTE, _pillow, output_dimensions
from trampoline_vision.results.errors import VisualizationError
from trampoline_vision.tracking.config import TrackerConfig
from trampoline_vision.tracking.session import TrackEvent


def tracking_record(result: TrackingFrameResult, events: tuple[TrackEvent, ...], config: TrackerConfig) -> dict:
    """Serialitza un instant sense duplicar totes les articulacions; preserva referències i motius no assignats."""
    source = result.frame.source
    detections = {d.detection_id: d for d in source.detections}
    candidates = []
    for candidate in result.frame.candidates:
        item = asdict(candidate)
        item["provenance"] = [asdict(detections[ref].provenance) for ref in candidate.source_detection_ids]
        if candidate.candidate_id in result.unassigned_candidate_ids:
            item["unassigned_reason"] = ("no_measurement" if candidate.measurement is None else
                                         "below_threshold" if candidate.measurement.score < config.confidence_threshold else
                                         "unconfirmed_or_unmatched")
        candidates.append(item)
    return {"schema_version": "1.0", "context": asdict(source.context), "source_status": source.source_status,
            "source_detections": len(source.detections), "candidates": candidates,
            "tracks": [asdict(t) for t in result.tracks], "unassigned_candidate_ids": list(result.unassigned_candidate_ids),
            "events": [asdict(e) for e in events]}


@dataclass(frozen=True)
class TrackingOverlayFrame:
    """Envolta el resultat per compartir el codificador de vídeo sense convertir-lo a deteccions fictícies."""

    result: TrackingFrameResult  # Resultat original immutable d'aquest instant.

    @property
    def context(self):
        """Exposa el context original que el codificador contrasta amb el vídeo descodificat."""
        return self.result.frame.source.context

    @property
    def source_status(self):
        """Conserva la distinció entre un JSON buit i un registre absent."""
        return self.result.frame.source.source_status

    @property
    def detections(self):
        """Permet al codificador comptar propostes originals sense interpretar-les com a tracks."""
        return self.result.frame.source.detections


def track_color(track_id: str) -> tuple[int, int, int]:
    """Tria un color estable entre fotogrames i processos; el text ID continua sent la identitat inequívoca."""
    return PALETTE[int.from_bytes(hashlib.sha256(track_id.encode()).digest()[:4], "big") % len(PALETTE)]


def render_tracking_frame(image, annotated: TrackingOverlayFrame, style):
    """Dibuixa caixes, IDs persistents i articulacions observades; els filtres només afecten les poses visibles."""
    result = annotated.result
    context = annotated.context
    if image.size != (context.width_px, context.height_px) or style.view != "all":
        raise VisualizationError("Tracking renderer requires matching dimensions and a single all view")
    Image, ImageDraw, ImageFont = _pillow()
    canvas = Image.new("RGB", output_dimensions(image.width, image.height, style), (15, 20, 28))
    canvas.paste(image.convert("RGB"), (0, HEADER_HEIGHT))
    draw, font = ImageDraw.Draw(canvas), ImageFont.load_default(size=13)
    candidates = {c.candidate_id: c for c in result.frame.candidates}
    detections = {d.detection_id: d for d in result.frame.source.detections}
    counts = {"observed_tracks": 0, "predicted_tracks": 0, "keypoints_drawn": 0, "finished_tracks": 0}
    for track in result.tracks:
        if track.state == "finished":
            counts["finished_tracks"] += 1
            continue
        observed = track.evidence == "observed"
        counts["observed_tracks" if observed else "predicted_tracks"] += 1
        color = track_color(track.track_id)
        if track.bbox is not None:
            box = track.bbox
            # El retall només és de dibuix; no es canvien les coordenades exportades.
            x0, x1 = max(0, min(image.width - 1, box.x_min)), max(0, min(image.width - 1, box.x_max))
            y0 = HEADER_HEIGHT + max(0, min(image.height - 1, box.y_min))
            y1 = HEADER_HEIGHT + max(0, min(image.height - 1, box.y_max))
            if observed:
                draw.rectangle((x0, y0, x1, y1), outline=color, width=2)
            else:
                for x in range(int(x0), int(x1), 8):
                    draw.line((x, y0, min(x + 4, x1), y0), fill=color, width=2)
                    draw.line((x, y1, min(x + 4, x1), y1), fill=color, width=2)
                for y in range(int(y0), int(y1), 8):
                    draw.line((x0, y, x0, min(y + 4, y1)), fill=color, width=2)
                    draw.line((x1, y, x1, min(y + 4, y1)), fill=color, width=2)
            if style.show_labels:
                draw.text((x0, max(HEADER_HEIGHT, y0 - 15)), f"{track.track_id} {track.evidence}", font=font,
                          fill=color, stroke_width=1, stroke_fill=(0, 0, 0))
        if observed:
            detection = detections[candidates[track.candidate_id].source_detection_ids[0]]
            visible = {i: p for i, p in enumerate(detection.keypoints)
                       if p.valid and p.in_frame and p.confidence >= style.min_confidence}
            if len(visible) < style.min_visible_points:
                continue
            for a, b in BODY25_EDGES:
                if a in visible and b in visible:
                    draw.line((visible[a].x, visible[a].y + HEADER_HEIGHT,
                               visible[b].x, visible[b].y + HEADER_HEIGHT), fill=color, width=2)
            for point in visible.values():
                draw.ellipse((point.x - 2, point.y + HEADER_HEIGHT - 2, point.x + 2, point.y + HEADER_HEIGHT + 2), fill=color)
            counts["keypoints_drawn"] += len(visible)
    draw.text((8, 5), f"TRACKING | frame {context.frame_index} | t={context.timestamp_s:.3f}s | {annotated.source_status}", font=font, fill="white")
    draw.text((8, 30), f"observed {counts['observed_tracks']} | predicted {counts['predicted_tracks']} | unassigned {len(result.unassigned_candidate_ids)}", font=font, fill="white")
    return canvas, {"tracking": counts}
