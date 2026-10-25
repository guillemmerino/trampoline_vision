"""Exploració aïllada de geometria i associació feble; no modifica el paquet ni els defaults.

Reutilitza contractes, ingestió i sessió 0.4.0. ByteTrack només existeix en
aquest experiment, amb API pública de trackers 2.6.1. No s'entrena ni s'infereix.
"""

import argparse
from collections import Counter
from contextlib import closing, ExitStack
from dataclasses import asdict, replace
import json
import math
from pathlib import Path
from uuid import uuid4

from trampoline_vision import __version__
from trampoline_vision.contracts.observations import (
    BODY25_NAMES, DetectionProvenance, FrameContext, FrameDetections, KeypointObservation, PersonDetection,
)
from trampoline_vision.contracts.tracking import BoundingBox
from trampoline_vision.ingestion.manifest import load_manifest
from trampoline_vision.ingestion.video import probe_video
from trampoline_vision.ingestion.openpose import iter_openpose_frames
from trampoline_vision.preparation.config import PreparationConfig, PoseBoxPolicy
from trampoline_vision.preparation.pipeline import prepare_frame
from trampoline_vision.results.tracking import tracking_record
from trampoline_vision.tracking.backend import OCSortBackend, BackendUpdate
from trampoline_vision.tracking.config import TrackerConfig
from trampoline_vision.tracking.session import TrackingSession


VARIANTS = {
    "reference": ("baseline", "ocsort"),
    "kp005": ("kp005", "ocsort"),
    "weighted": ("weighted", "ocsort"),
    "byte_high": ("baseline", "byte_high"),
    "byte_weak": ("baseline", "byte_weak"),
    "byte_weighted": ("weighted", "byte_weak"),
    "byte_strict": ("baseline", "byte_strict"),
}


def weighted_quantile(points, axis: str, quantile: float) -> float:
    """Retorna una coordenada observada en el quantil ponderat per confiança, sense interpolar punts."""
    ordered = sorted(points, key=lambda point: getattr(point, axis))
    threshold = sum(p.confidence for p in ordered) * quantile
    accumulated = 0.0
    for point in ordered:
        accumulated += point.confidence
        if accumulated >= threshold:
            return getattr(point, axis)
    return getattr(ordered[-1], axis)


def prepare_experiment(source, mode: str):
    """Construeix candidats amb selecció 0.05 o extensió ponderada 5–95%; conserva totes les observacions."""
    policy = PoseBoxPolicy(min_keypoint_confidence=.05 if mode == "kp005" else 0)
    frame = prepare_frame(source, PreparationConfig(box=policy))
    if mode != "weighted":
        return frame
    detections = {d.detection_id: d for d in source.detections}
    candidates = []
    for candidate in frame.candidates:
        if candidate.measurement is None:
            candidates.append(candidate)
            continue
        points = [p for p in detections[candidate.source_detection_ids[0]].keypoints if p.valid and p.in_frame]
        x0, x1 = weighted_quantile(points, "x", .05), weighted_quantile(points, "x", .95)
        y0, y1 = weighted_quantile(points, "y", .05), weighted_quantile(points, "y", .95)
        minimum = max(policy.min_span_px, policy.min_span_image_ratio * math.hypot(source.context.width_px, source.context.height_px))
        issues = candidate.issues + ("experimental_weighted_extent",)
        if x1 - x0 < minimum or y1 - y0 < minimum:
            candidate = replace(candidate, measurement=None, issues=issues + ("weighted_extent_insufficient_span",))
        else:
            dx, dy = (x1 - x0) * policy.padding_ratio, (y1 - y0) * policy.padding_ratio
            candidate = replace(candidate, measurement=replace(candidate.measurement,
                                bbox=BoundingBox(x0 - dx, y0 - dy, x1 + dx, y1 + dy)), issues=issues)
        candidates.append(candidate)
    return replace(frame, candidates=tuple(candidates))


class ExperimentalBackend(OCSortBackend):
    """Port d'experiment amb llindars alta/baixa separats; cap canvi al registre de backends de producció."""

    def __init__(self, config, fps, kind):
        """Inicialitza ByteTrack públic o OC-SORT; en ByteTrack el naixement requereix score >=0.1."""
        super().__init__(config, fps)
        self.kind = kind
        self.confirmed_ids = lambda: set()  # Callback del registre de domini, només per a l'experiment strict.
        self.exposed_pending = set()  # IDs pendents exposats inicialment amb mesura forta.
        if kind.startswith("byte"):
            from trackers import ByteTrackTracker
            self.tracker = ByteTrackTracker(lost_track_buffer=config.lost_buffer, frame_rate=fps,
                                           track_activation_threshold=.1, high_conf_det_threshold=.1,
                                           minimum_consecutive_frames=1, minimum_iou_threshold=config.min_iou)

    def update(self, frame):
        """Filtra admissió baixa sense perdre la partició de candidats; els febles no creen tracks nous."""
        floor = .1 if self.kind == "byte_high" else .02 if self.kind.startswith("byte") else 0
        eligible = tuple(c for c in frame.candidates if c.measurement is None or c.measurement.score >= floor)
        ignored = tuple((c.candidate_id, -1) for c in frame.candidates
                        if c.measurement is not None and c.measurement.score < floor)
        response = super().update(replace(frame, candidates=eligible))
        if self.kind == "byte_strict":
            scores = {c.candidate_id: c.measurement.score for c in eligible if c.measurement is not None}
            confirmed = self.confirmed_ids()
            strong = {tid for cid, tid in response.assignments if tid >= 0 and scores[cid] >= .1}
            allowed = confirmed | self.exposed_pending | strong
            assignments = tuple((cid, -1 if tid >= 0 and tid not in confirmed and scores[cid] < .1 else tid)
                                for cid, tid in response.assignments)
            alive = tuple((tid, box) for tid, box in response.alive if tid in allowed)
            self.exposed_pending = (self.exposed_pending | strong) & {tid for tid, _ in response.alive}
            response = BackendUpdate(assignments, alive)
        return BackendUpdate(response.assignments + ignored, response.alive)


def synthetic_frame(index, confidence):
    """Crea una persona sintètica immòbil per comprovar la política de confiança, sense vídeo real."""
    coords = {"neck": (50, 20), "right_shoulder": (40, 30), "left_shoulder": (60, 30),
              "mid_hip": (50, 60), "right_knee": (45, 80), "left_knee": (55, 80)}
    points = tuple(KeypointObservation(n, *coords[n], confidence, True, True) if n in coords else
                   KeypointObservation(n, None, None, 0, False, None) for n in BODY25_NAMES)
    person = PersonDetection(str(index), points, DetectionProvenance("synthetic", "frame", index, 0, "synthetic", "unknown"))
    return prepare_frame(FrameDetections(FrameContext("synthetic", index, index / 30, 1 / 30, 100, 100), (person,), "present"))


def smoke_check() -> dict:
    """Demostra que una proposta 0.05 no inicia identitat i que pot mantenir-ne una iniciada amb evidència forta."""
    backend = ExperimentalBackend(TrackerConfig(), 30, "byte_weak")
    for i in range(3):
        result = backend.update(synthetic_frame(i, .05))
        assert not result.alive
    for i in range(3, 8):
        result = backend.update(synthetic_frame(i, .8))
    identities = {tid for _, tid in result.assignments if tid >= 0}
    assert len(identities) == 1
    weak = backend.update(synthetic_frame(8, .05))
    assert {tid for _, tid in weak.assignments if tid >= 0} == identities
    strict = TrackingSession(TrackerConfig(), 30)
    strict.backend = ExperimentalBackend(strict.config, 30, "byte_strict")
    strict.backend.confirmed_ids = lambda: set(strict.live)
    for i, confidence in enumerate((.8, .8, .05, .8, .05, .8, .8, .8, .05)):
        result = strict.update(synthetic_frame(i, confidence))
        if i < 7:
            assert not result.tracks, "Weak observations must not confirm a birth"
        else:
            assert len(result.tracks) == 1 and result.tracks[0].evidence == "observed"
    return {"weak_only_cannot_spawn": True, "weak_can_update_existing": True,
            "strict_birth_requires_three_consecutive_strong_matches": True,
            "strict_confirmed_track_accepts_weak_measurement": True}


def main() -> None:
    """Executa les variants seleccionades en una lectura seqüencial, amb el mateix temps i escalfament per totes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--variants", nargs="+", choices=tuple(VARIANTS), default=list(VARIANTS))
    args = parser.parse_args()
    if args.output_dir.exists():
        raise ValueError("Output directory already exists")
    manifest = load_manifest(args.manifest)
    video = probe_video(manifest.video_path, manifest.case_id)
    assert __version__ == "0.4.0", "Use the frozen 0.4.0 runtime"
    smoke = smoke_check()
    args.output_dir.mkdir(parents=True)
    sessions = {}
    variants = {name: VARIANTS[name] for name in args.variants}
    for name, (_, kind) in variants.items():
        session = TrackingSession(TrackerConfig(), video.fps)
        session.backend = ExperimentalBackend(session.config, video.fps, kind)
        session.backend.confirmed_ids = lambda current=session: set(current.live)
        sessions[name] = session
    counters = {name: Counter() for name in variants}
    run_ids = {name: str(uuid4()) for name in variants}
    with ExitStack() as stack:
        streams = {(name, clip): stack.enter_context((args.output_dir / f"{name}-{clip}.frames.jsonl").open("x", encoding="utf-8"))
                   for name in variants for clip in ("baseline", "flight")}
        raw_frames = stack.enter_context(closing(iter_openpose_frames(manifest, video)))
        for index in range(510):
            source = next(raw_frames)
            selected = index < 90 or index >= 420
            prepared = {mode: prepare_experiment(source, mode) for mode in ("baseline", "kp005", "weighted")}
            for name, (geometry, kind) in variants.items():
                session = sessions[name]
                result = session.update(prepared[geometry])
                if not selected:
                    continue
                record = tracking_record(result, session.events, session.config)
                record["run_id"] = run_ids[name]
                record["experiment"] = {"name": name, "backend": kind, "geometry": geometry}
                # L'ID és opac: l'exportació experimental explicita ByteTrack en lloc del prefix intern de la sessió reutilitzada.
                if kind.startswith("byte"):
                    for item in record["tracks"] + record["events"]:
                        item["track_id"] = item["track_id"].replace("ocsort:", "bytetrack:", 1)
                clip = "baseline" if index < 90 else "flight"
                streams[(name, clip)].write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
                counters[name]["observed"] += sum(t.evidence == "observed" for t in result.tracks)
                counters[name]["predicted"] += sum(t.state == "lost" for t in result.tracks)
                counters[name]["confirmed"] += sum(e.kind == "confirmed" for e in session.events)
            if index % 100 == 0:
                print(f"Processed {index}/509", flush=True)
    summary = {"software_version": __version__, "trackers_version": "2.6.1", "smoke": smoke,
               "range": {"processed": [0, 509], "exported": [[0, 89], [420, 509]]},
               "variants": {name: {"geometry": geometry, "backend": kind, "counts": dict(counters[name])}
                            for name, (geometry, kind) in variants.items()},
               "confidence_policy": {"byte_high": {"high": .1, "floor": .1, "activation": .1},
                                     "byte_weak": {"high": .1, "floor": .02, "activation": .1}},
               "notes": ["exploratory_not_production", "same_domain_birth_streak_3",
                         "standard_byte_birth_streak_can_include_weak_matches",
                         "byte_strict_requires_three_strong_public_matches_for_birth", "no_new_inference"]}
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
