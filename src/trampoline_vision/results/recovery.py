"""Diagnòstic i overlay de fragments: IDs del tracker preservats, cap actor reconstruït."""

from dataclasses import asdict, dataclass

from trampoline_vision.contracts.recovery import TrackingTraceFrame
from trampoline_vision.results.errors import VisualizationError
from trampoline_vision.results.overlay import HEADER_HEIGHT, _pillow, output_dimensions
from trampoline_vision.results.tracking import track_color


def fragment_record(fragment):
    """Serialitza observacions auditables i resums geomètrics/confiança, sense probabilitats d'identitat."""
    first, last = fragment.samples[0], fragment.samples[-1]
    scores = [s.candidate.candidate.measurement.score for s in fragment.samples]
    duration = last.context.timestamp_s + last.context.duration_s - first.context.timestamp_s
    return {**asdict(fragment), 'first_frame_index': first.context.frame_index, 'last_frame_index': last.context.frame_index,
            'start_s': first.context.timestamp_s, 'last_observed_s': last.context.timestamp_s,
            'end_s_exclusive': last.context.timestamp_s + last.context.duration_s,
            'observed_samples': len(fragment.samples), 'observed_duration_s': duration,
            'first_bbox': asdict(first.track.bbox), 'last_bbox': asdict(last.track.bbox),
            'measurement_score': {'min': min(scores), 'max': max(scores), 'mean': sum(scores)/len(scores),
                                  'meaning': 'input_measurement_score_not_identity_quality'},
            'candidate_issues': sorted({issue for s in fragment.samples for issue in s.candidate.candidate.issues})}


def gap_record(gap):
    """Diferencia buit de mesures, prediccions amb/sense caixa i finalització del tracker."""
    first, last = gap.samples[0], gap.samples[-1]
    return {**asdict(gap), 'first_frame_index': first.context.frame_index, 'last_frame_index': last.context.frame_index,
            'start_s': first.context.timestamp_s, 'end_s_exclusive': last.context.timestamp_s + last.context.duration_s,
            'lost_samples': sum(s.track.state == 'lost' for s in gap.samples),
            'predicted_boxes': sum(s.track.state == 'lost' and s.track.bbox is not None for s in gap.samples),
            'finished_samples': sum(s.track.state == 'finished' for s in gap.samples),
            'elapsed_since_last_observation_s': last.context.timestamp_s - first.track.last_observed_timestamp_s}


def diagnostics(result, *, enabled=True):
    """Resume què arriba al futur reconstructor; els comptadors d'actors/unions no s'inventen."""
    track_ids = sorted({s.track_id for f in result.trace.frames for s in f.tracks})
    by_track = {tid: {'track_id': tid, 'fragment_ids': [], 'gap_ids': []} for tid in track_ids}
    for fragment in result.fragments:
        by_track[fragment.track_id]['fragment_ids'].append(fragment.fragment_id)
    for gap in result.gaps:
        by_track[gap.track_id]['gap_ids'].append(gap.gap_id)
    return {'status': 'fragments_prepared' if enabled else 'disabled', 'policy': result.policy,
            'totals': {'frames': len(result.trace.frames), 'tracks': len(track_ids),
                       'fragments': len(result.fragments), 'gaps': len(result.gaps),
                       'observed_samples': sum(s.evidence == 'observed' for f in result.trace.frames for s in f.tracks),
                       'lost_samples': sum(s.state == 'lost' for f in result.trace.frames for s in f.tracks),
                       'finished_samples': sum(s.state == 'finished' for f in result.trace.frames for s in f.tracks),
                       'missing_source_frames': sum(f.source_status == 'missing' for f in result.trace.frames),
                       'candidates': sum(len(f.candidates) for f in result.trace.frames),
                       'unassigned_candidates': sum(len(f.unassigned_candidate_ids) for f in result.trace.frames),
                       'single_observation_fragments': sum(len(f.samples) == 1 for f in result.fragments)},
            'tracks': list(by_track.values()),
            'fragments': [{k: v for k, v in fragment_record(f).items() if k != 'samples'} for f in result.fragments],
            'gaps': [{k: v for k, v in gap_record(g).items() if k != 'samples'} for g in result.gaps],
            'actor_reconstruction': 'not_executed', 'identity_accuracy': 'not_evaluated'}


def sample_labels(result):
    """Indexa fragment/buit per frame i track sense afirmar observacions dins dels buits."""
    labels = {}
    for fragment in result.fragments:
        for sample in fragment.samples:
            labels[(sample.context.frame_index, sample.track.track_id)] = (fragment.fragment_id, None)
    for gap in result.gaps:
        for sample in gap.samples:
            labels[(sample.context.frame_index, sample.track.track_id)] = (gap.previous_fragment_id, gap.gap_id)
    return labels


def annotated_frames(result, *, enabled=True):
    """Ofereix al codificador la traça completa i l'etiqueta corresponent a cada mostra."""
    labels = sample_labels(result) if enabled else {}
    for frame in result.trace.frames:
        yield FragmentOverlayFrame(frame, tuple((s.track_id, *labels.get((frame.context.frame_index, s.track_id), (None, None))) for s in frame.tracks))


@dataclass(frozen=True)
class FragmentOverlayFrame:
    """Adaptació mínima de la traça al codificador de vídeo ja existent."""

    frame: TrackingTraceFrame
    labels: tuple[tuple[str, str | None, str | None], ...]

    @property
    def context(self):
        """Conserva el context original per a la validació de PTS i dimensions."""
        return self.frame.context

    @property
    def source_status(self):
        """Manté els registres absents diferenciats dels negatius del detector."""
        return self.frame.source_status

    @property
    def detections(self):
        """El codificador només n'usa el recompte; els candidats no es converteixen en poses."""
        return self.frame.candidates


def render_fragment_frame(image, annotated, style):
    """Dibuixa caixes originals/predites i fragment_id + track_id, sense omplir buits."""
    context = annotated.context
    if style.view != 'all' or image.size != (context.width_px, context.height_px):
        raise VisualizationError('Fragment renderer requires matching original geometry and all view')
    Image, ImageDraw, ImageFont = _pillow()
    canvas = Image.new('RGB', output_dimensions(image.width, image.height, style), (15, 20, 28))
    canvas.paste(image.convert('RGB'), (0, HEADER_HEIGHT))
    draw, font = ImageDraw.Draw(canvas), ImageFont.load_default(size=12)
    labels = {tid: (fid, gid) for tid, fid, gid in annotated.labels}
    counts = {'observed': 0, 'predicted': 0, 'finished': 0, 'predicted_without_box': 0}
    for sample in annotated.frame.tracks:
        if sample.state == 'finished':
            counts['finished'] += 1
            continue
        observed = sample.evidence == 'observed'
        counts['observed' if observed else 'predicted'] += 1
        if sample.bbox is None:
            counts['predicted_without_box'] += 1
            continue
        fid, gid = labels[sample.track_id]
        color = track_color(fid or sample.track_id)
        box = sample.bbox
        x0, x1 = [max(0, min(image.width-1, x)) for x in (box.x_min, box.x_max)]
        y0, y1 = [HEADER_HEIGHT + max(0, min(image.height-1, y)) for y in (box.y_min, box.y_max)]
        if observed:
            draw.rectangle((x0, y0, x1, y1), outline=color, width=2)
        else:
            for x in range(int(x0), int(x1), 8):
                for y in (y0, y1):
                    draw.line((x, y, min(x+4, x1), y), fill=color, width=2)
            for y in range(int(y0), int(y1), 8):
                for x in (x0, x1):
                    draw.line((x, y, x, min(y+4, y1)), fill=color, width=2)
        if style.show_labels:
            # El prefix de fragment inclou el track; només mostrem l'ordinal
            # per no repetir-lo i tapar actors propers. L'ID complet és al JSONL.
            fragment_label = 'F' + fid.rsplit(':', 1)[-1] if fid else 'disabled'
            label = f'{sample.track_id} | {fragment_label}'
            if gid:
                label += ' | GAP'
            draw.text((x0, max(HEADER_HEIGHT, y0-14)), label, font=font, fill=color, stroke_width=1, stroke_fill='black')
    draw.text((8, 4), f'FRAGMENTS | frame {context.frame_index} | t={context.timestamp_s:.3f}s | {annotated.source_status}', font=font, fill='white')
    draw.text((8, 27), f'observed {counts["observed"]} | predicted {counts["predicted"]} | actors not reconstructed', font=font, fill='white')
    return canvas, {'fragments': counts}
