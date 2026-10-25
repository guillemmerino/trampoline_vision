"""Dibuix de deteccions BODY_25, independent del lector i de la codificació del vídeo.

Els filtres només decideixen què es veu. Les observacions immutables no es
modifiquen i els colors identifiquen deteccions locals, no trajectòries.
Pillow es carrega quan es dibuixa, mantenint la ingestió sense dependències visuals.
"""

from dataclasses import dataclass
import math

from trampoline_vision.contracts.observations import FrameDetections, PersonBoxDetection
from trampoline_vision.results.errors import VisualizationError


# Connexions anatòmiques BODY_25; no s'inventa una aresta si falta un extrem.
BODY25_EDGES = (
    (0, 1), (1, 2), (2, 3), (3, 4), (1, 5), (5, 6), (6, 7),
    (1, 8), (8, 9), (9, 10), (10, 11), (8, 12), (12, 13), (13, 14),
    (0, 15), (15, 17), (0, 16), (16, 18),
    (14, 19), (19, 20), (14, 21), (11, 22), (22, 23), (11, 24),
)
HEADER_HEIGHT = 64  # Fora de la imatge original: no tapa el gimnasta quan arriba al marge superior.
PALETTE = ((0, 230, 255), (255, 210, 0), (255, 90, 170), (80, 255, 120),
           (255, 135, 40), (170, 150, 255), (255, 255, 255), (70, 170, 255))


@dataclass(frozen=True)
class RenderStyle:
    """Opcions exclusives del dibuix, sense conseqüències sobre el tracking futur.

    all mostra cada punt observat dins la imatge; filtered aplica confiança i
    mínim de punts visibles per detecció; compare posa les dues vistes en paral·lel.
    Aquests llindars són ajudes de revisió, no criteris de qualitat esportiva.
    """

    view: str = "filtered"  # all, filtered o compare; compare duplica l'amplada.
    min_confidence: float = 0.25  # S'aplica per articulació a la vista filtrada.
    min_visible_points: int = 6  # Punts que superen el filtre i són dins la imatge.
    show_labels: bool = True  # IDs de detecció del fotograma; no són IDs de persona seguits.

    def __post_init__(self) -> None:
        """Valida les opcions abans de descodificar o crear una sortida."""
        if not isinstance(self.view, str) or self.view not in {"all", "filtered", "compare"}:
            raise VisualizationError("view must be all, filtered or compare")
        if isinstance(self.min_confidence, bool) or not isinstance(self.min_confidence, (int, float)) or not math.isfinite(self.min_confidence) or not 0 <= self.min_confidence <= 1:
            raise VisualizationError("min_confidence must be finite and within [0, 1]")
        if type(self.min_visible_points) is not int or not 1 <= self.min_visible_points <= 25:
            raise VisualizationError("min_visible_points must be an integer within [1, 25]")
        if type(self.show_labels) is not bool:
            raise VisualizationError("show_labels must be boolean")


def _pillow():
    """Carrega la dependència opcional de dibuix amb un error d'instal·lació útil."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise VisualizationError("Visualization requires Pillow. Install trampoline-vision[visualization] or use Docker CPU.") from exc
    return Image, ImageDraw, ImageFont


def output_dimensions(width: int, height: int, style: RenderStyle) -> tuple[int, int]:
    """Calcula mida exportada, amb capçalera i padding màxim d'un píxel per a H.264.

    Les imatges es copien a escala 1:1. Els píxels afegits no deformen les
    coordenades; compare situa el segon panell a X=width i tots dos a Y=64.
    """
    panel_width = width * (2 if style.view == "compare" else 1)
    return panel_width + panel_width % 2, height + HEADER_HEIGHT + (height + HEADER_HEIGHT) % 2


def _draw_panel(image, observations: FrameDetections, style: RenderStyle, view: str):
    """Dibuixa un panell sobre una còpia i retorna els recomptes realment visibles.

    Un punt fora de marc no es trasllada al marge, ni es dibuixa una línia amb
    un extrem absent. El mínim de punts només afecta la vista filtered.
    """
    _, ImageDraw, ImageFont = _pillow()
    result = image.convert("RGB").copy()
    draw = ImageDraw.Draw(result)
    font = ImageFont.load_default(size=13)
    confidence = style.min_confidence if view == "filtered" else 0.0
    minimum = style.min_visible_points if view == "filtered" else 1
    counts = {"detections_drawn": 0, "keypoints_drawn": 0, "edges_drawn": 0}
    for index, detection in enumerate(observations.detections):
        if isinstance(detection, PersonBoxDetection):
            if view == "filtered" and detection.score < confidence:
                continue
            box = detection.bbox
            color = PALETTE[index % len(PALETTE)]
            draw.rectangle((box.x_min, box.y_min, box.x_max, box.y_max), outline=color, width=2)
            if style.show_labels:
                draw.text((box.x_min, max(0, box.y_min-17)), detection.detection_id, font=font, fill=color)
            counts["detections_drawn"] += 1
            continue
        visible = {i: p for i, p in enumerate(detection.keypoints)
                   if p.valid and p.in_frame and p.confidence >= confidence}
        if len(visible) < minimum:
            continue
        color = PALETTE[index % len(PALETTE)]
        counts["detections_drawn"] += 1
        counts["keypoints_drawn"] += len(visible)
        for left, right in BODY25_EDGES:
            if left in visible and right in visible:
                a, b = visible[left], visible[right]
                draw.line((a.x, a.y, b.x, b.y), fill=color, width=2)
                counts["edges_drawn"] += 1
        for point in visible.values():
            draw.ellipse((point.x - 2, point.y - 2, point.x + 2, point.y + 2), fill=color)
        if style.show_labels:
            anchor_x = min(p.x for p in visible.values())
            anchor_y = max(0, min(p.y for p in visible.values()) - 17)
            # El text es col·loca dins del panell sense desplaçar les articulacions.
            text_width = draw.textbbox((0, 0), detection.detection_id, font=font)[2]
            anchor_x = max(0, min(anchor_x, image.width - text_width - 2))
            draw.text((anchor_x, anchor_y), detection.detection_id, font=font, fill=color,
                      stroke_width=1, stroke_fill=(0, 0, 0))
    return result, counts


def render_frame(image, observations: FrameDetections, style: RenderStyle):
    """Combina panells i capçalera, retornant imatge RGB i recomptes per vista.

    L'entrada ha de ser exactament el fotograma descrit pel context. No es
    carrega cap model, ni es fusionen o es descarten dades d'origen.
    """
    context = observations.context
    if image.size != (context.width_px, context.height_px):
        raise VisualizationError("Image dimensions do not match FrameContext")
    Image, ImageDraw, ImageFont = _pillow()
    canvas = Image.new("RGB", output_dimensions(image.width, image.height, style), (15, 20, 28))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=15)
    views = ("all", "filtered") if style.view == "compare" else (style.view,)
    stats = {}
    for panel_index, view in enumerate(views):
        panel, counts = _draw_panel(image, observations, style, view)
        offset = panel_index * image.width
        canvas.paste(panel, (offset, HEADER_HEIGHT))
        stats[view] = counts
        line1 = f"{view.upper()} | frame {context.frame_index} | source t={context.timestamp_s:.3f}s | {observations.source_status}"
        line2 = f"detections {counts['detections_drawn']}/{len(observations.detections)} | points {counts['keypoints_drawn']} | detection IDs, NO tracking"
        if view == "filtered":
            line2 += f" | conf>={style.min_confidence:g}, min={style.min_visible_points}"
        draw.text((offset + 8, 5), line1, font=font, fill=(240, 245, 250))
        draw.text((offset + 8, 30), line2, font=font, fill=(185, 200, 220))
    return canvas, stats
