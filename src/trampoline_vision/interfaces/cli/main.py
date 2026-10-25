"""Interfície de terminal per inspecció, visualització, tracking i avaluació a CPU.

Tradueix arguments a un cas d'ús, comprova les sortides i presenta errors.
La lectura de vídeo i OpenPose viu a ingestion; els recomptes viuen a
application. Les dependències de dibuix només es carreguen en visualitzar;
els backends pesants es carreguen només en executar tracking. Es pot invocar des de
trampoline-vision o python -m trampoline_vision.
"""

import argparse
import json
import math
from pathlib import Path
import shutil
import sys
import tempfile

from trampoline_vision.application.recovery import inspect_tracking_fragments
from trampoline_vision.application.recovery_audit import audit_tracking_recovery
from trampoline_vision.ingestion.recovery_config import load_fragmentation_config
from trampoline_vision.recovery.config import FragmentationConfig
from trampoline_vision.application.inspection import inspect_case
from trampoline_vision.application.visualization import visualize_case
from trampoline_vision.application.tracking import track_case
from trampoline_vision.application.tracking_evaluation import evaluate_tracking
from trampoline_vision.infrastructure.artifacts import publish_exclusive
from trampoline_vision.ingestion.errors import InputError
from trampoline_vision.ingestion.manifest import load_inspection_config, load_manifest, load_visualization_config
from trampoline_vision.ingestion.video import probe_video
from trampoline_vision.ingestion.tracking_config import load_tracking_config
from trampoline_vision.results.overlay import RenderStyle


def _render_progress(done: int, total: int) -> None:
    """Informa periòdicament per stderr sense barrejar el progrés amb els artefactes."""
    if done == 1 or done % 100 == 0 or done == total:
        print(f"Rendering {done}/{total} frames", file=sys.stderr, flush=True)


def _run_visualization(args) -> int:
    """Resol opcions de visualització i delega la generació i verificació dels artefactes.

    Els valors explícits de terminal prevalen sobre render de la configuració.
    El sondeig i els lectors són els mateixos del pas 2, sense inferència nova.
    """
    config_policy, settings = "report", {}
    if args.config:
        manifest_path, config_policy, settings = load_visualization_config(args.config)
    else:
        manifest_path = args.manifest
    for key in ("view", "min_confidence", "min_visible_points", "show_labels"):
        value = getattr(args, key)
        if value is not None:
            settings[key] = value
    style = RenderStyle(**settings)
    manifest = load_manifest(manifest_path)
    video = probe_video(manifest.video_path, manifest.case_id, ffprobe=args.ffprobe, timeout_s=args.probe_timeout)
    report = args.report if args.report else args.output.with_suffix(".json")
    visualize_case(manifest, video, args.output, report, style=style, start_s=args.start, end_s=args.end,
                   missing_frames_policy=args.missing_frames_policy or config_policy,
                   ffprobe=args.ffprobe, probe_timeout_s=args.probe_timeout, progress=_render_progress,
                   protected_paths=(args.config,) if args.config else ())
    print(f"Visualization complete: {args.output.resolve()}")
    print(f"Report: {report.resolve()}")
    return 0


def _publish(staged: Path, destination: Path) -> None:
    """Copia un artefacte temporal a un destí nou sense sobreescriure fitxers.

    El mode x reserva el nom de forma exclusiva. Si falla la còpia, elimina
    només el fitxer creat per aquesta mateixa operació. No és una publicació
    atòmica ni una transacció conjunta entre informe i JSONL; una interrupció
    del procés encara pot deixar un fitxer parcial.
    """
    # Només eliminarem un fitxer si l’ha creat aquesta crida; mai un destí preexistent.
    created = False
    try:
        with destination.open("x", encoding="utf-8", newline="\n") as target:
            created = True
            with staged.open(encoding="utf-8") as source:
                shutil.copyfileobj(source, target)
    except Exception:
        if created:
            destination.unlink(missing_ok=True)
        raise


def _run_tracking(args) -> int:
    """Resol el pipeline de seguiment i delega exportació, vídeo opcional i informe a application."""
    settings = load_tracking_config(args.config)
    manifest = load_manifest(settings.manifest_path)
    video = probe_video(manifest.video_path, manifest.case_id, ffprobe=args.ffprobe, timeout_s=args.probe_timeout)
    frames = args.frames_output or args.output.with_suffix(".frames.jsonl")
    track_case(manifest, video, args.output, frames, preparation=settings.preparation, tracker=settings.tracker,
               video_output=args.video_output, start_s=args.start, end_s=args.end,
               missing_frames_policy=settings.missing_frames_policy, ffprobe=args.ffprobe,
               probe_timeout_s=args.probe_timeout, progress=_render_progress,
               protected_paths=(args.config, *settings.protected_paths))
    print(f"Tracking complete: {args.output.resolve()}")
    print(f"Frame export: {frames.resolve()}")
    return 0


def _run_fragment_inspection(args) -> int:
    """Diagnostica tracking acabat amb perfils de preparació, sense inferència ni associació."""
    config = load_fragmentation_config(args.config) if args.config else FragmentationConfig()
    inspect_tracking_fragments(args.tracking_report, args.output, tracks_path=args.tracks,
        video_path=args.video, fragments_output=args.fragments_output, video_output=args.video_output,
        config=config, ffprobe=args.ffprobe, probe_timeout_s=args.probe_timeout, progress=_render_progress,
        protected_paths=(args.config,) if args.config else ())
    print(f"Fragment inspection complete: {args.output.resolve()}")
    return 0


def _run_tracking_evaluation(args) -> int:
    """Publica diagnòstics d'anotacions revisades sense carregar dependències de tracking o vídeo."""
    destination = args.output.resolve()
    if destination.exists() or destination in {args.tracks.resolve(), args.annotations.resolve()}:
        raise InputError("Refusing to overwrite evaluation input or existing output")
    result = evaluate_tracking(args.tracks, args.annotations)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="trampoline-evaluate-") as temporary:
        staged = Path(temporary) / "evaluation.json"
        staged.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        publish_exclusive(staged, destination)
    print(f"Tracking evaluation complete: {destination}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Executa el cas d'ús seleccionat i retorna 0 en èxit o 2 per errors esperats.

    argv permet injectar arguments en proves; None utilitza els de terminal.
    Resol configuració/manifest, rebutja sortides existents, sondeja el vídeo,
    llegeix deteccions en temporals i després publica els artefactes. La branca
    de visualització delega codificació i publicació al seu cas d'ús.
    A inspect, sense --output envia l'informe a stdout. Retorna 0 en completar la
    lectura amb o sense avisos i 2 per errors esperats d'entrada o sortida.
    argparse gestiona per separat l'ajuda i els errors de sintaxi d'arguments.
    """
    parser = argparse.ArgumentParser(prog="trampoline-vision", description="Inspect, track, evaluate and prepare trajectory fragments on CPU.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect = subparsers.add_parser("inspect", help="Read recorded BODY_25 detections; no inference, tracking or scoring.")
    # Es parteix d’un manifest directe o d’una configuració; exigir-ne un evita ambigüitat.
    inputs = inspect.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--manifest", type=Path)
    inputs.add_argument("--config", type=Path, help="Executable inspection config (not a design-only pipeline).")
    inspect.add_argument("--missing-frames-policy", choices=["report", "error"], default=None)
    inspect.add_argument("--ffprobe", default="ffprobe", help="Executable name or path.")
    inspect.add_argument("--probe-timeout", type=float, default=120.0, metavar="SECONDS")
    inspect.add_argument("--output", type=Path, help="Write a summary JSON, refusing an existing file; default is stdout.")
    inspect.add_argument("--frames-output", type=Path, help="Optional internal observations JSONL (potentially large).")
    visual = subparsers.add_parser("visualize", help="Render observed BODY_25 detections; no tracking or scoring.")
    sources = visual.add_mutually_exclusive_group(required=True)
    sources.add_argument("--manifest", type=Path)
    sources.add_argument("--config", type=Path, help="Executable visualization configuration.")
    visual.add_argument("--output", type=Path, required=True, help="New MP4 path; existing files are refused.")
    visual.add_argument("--report", type=Path, help="JSON report path; default is output with .json suffix.")
    visual.add_argument("--start", type=float, default=0.0, metavar="SECONDS")
    visual.add_argument("--end", type=float, default=None, metavar="SECONDS", help="Exclusive presentation-time limit.")
    visual.add_argument("--view", choices=["all", "filtered", "compare"], default=None)
    visual.add_argument("--min-confidence", type=float, default=None)
    visual.add_argument("--min-visible-points", type=int, default=None)
    visual.add_argument("--labels", dest="show_labels", action=argparse.BooleanOptionalAction, default=None)
    visual.add_argument("--missing-frames-policy", choices=["report", "error"], default=None)
    visual.add_argument("--ffprobe", default="ffprobe")
    visual.add_argument("--probe-timeout", type=float, default=120.0, metavar="SECONDS")
    track = subparsers.add_parser("track", help="Track recorded detections and export auditable identities; no scoring.")
    track.add_argument("--config", type=Path, required=True)
    track.add_argument("--output", type=Path, required=True, help="New summary JSON path.")
    track.add_argument("--frames-output", type=Path, help="JSONL path; default is output stem with .frames.jsonl.")
    track.add_argument("--video-output", type=Path, help="Optional annotated MP4 with observed and predicted boxes.")
    track.add_argument("--start", type=float, default=0.0)
    track.add_argument("--end", type=float, default=None)
    track.add_argument("--ffprobe", default="ffprobe")
    track.add_argument("--probe-timeout", type=float, default=120.0)
    evaluate = subparsers.add_parser("evaluate-tracking", help="Evaluate manually reviewed sparse identity annotations.")
    evaluate.add_argument("--tracks", type=Path, required=True)
    evaluate.add_argument("--annotations", type=Path, required=True)
    evaluate.add_argument("--output", type=Path, required=True)
    fragments = subparsers.add_parser("inspect-fragments", help="Inspect fragments of completed full-video tracking; no actor reconstruction.")
    fragments.add_argument("--tracking-report", type=Path, required=True, help="Report produced by track over the complete video.")
    fragments.add_argument("--tracks", type=Path, help="Override input JSONL path, e.g. after moving artifacts from Docker.")
    fragments.add_argument("--video", type=Path, help="Override original video path for coverage verification and optional rendering.")
    fragments.add_argument("--config", type=Path, help="Executable fragmentation profile; draft recovery profiles are refused.")
    fragments.add_argument("--output", type=Path, required=True, help="New diagnostic JSON report.")
    fragments.add_argument("--fragments-output", type=Path, help="New fragment/gap JSONL; default: output stem + .fragments.jsonl.")
    fragments.add_argument("--video-output", type=Path, help="Optional MP4 with original track IDs and fragment IDs.")
    fragments.add_argument("--ffprobe", default="ffprobe")
    fragments.add_argument("--probe-timeout", type=float, default=120.0)
    audit = subparsers.add_parser('audit-recovery', help='Experimental global link proposals; original tracking is preserved, no apply.')
    audit.add_argument('--tracking-report', type=Path, required=True)
    audit.add_argument('--config', type=Path, required=True, help='Explicit executable experimental audit profile.')
    audit.add_argument('--output', type=Path, required=True)
    audit.add_argument('--links-output', type=Path)
    audit.add_argument('--tracks', type=Path)
    audit.add_argument('--video', type=Path)
    audit.add_argument('--appearance-cache', type=Path, help='Existing native SQLite; never infer missing descriptors.')
    audit.add_argument('--detections', type=Path, help='Override original detection file for cache content verification.')
    audit.add_argument('--ffprobe', default='ffprobe')
    audit.add_argument('--probe-timeout', type=float, default=120.)
    args = parser.parse_args(argv)
    try:
        if args.command == "evaluate-tracking":
            return _run_tracking_evaluation(args)
        if not math.isfinite(args.probe_timeout) or args.probe_timeout <= 0:
            raise InputError("--probe-timeout must be positive")
        if args.command == 'audit-recovery':
            audit_tracking_recovery(args.tracking_report, args.output, config_file=args.config,
                tracks_path=args.tracks, video_path=args.video, appearance_cache=args.appearance_cache,
                detections_path=args.detections, links_output=args.links_output,
                ffprobe=args.ffprobe, probe_timeout_s=args.probe_timeout)
            print(f'Recovery audit complete (experimental, not applied): {args.output.resolve()}')
            return 0
        if args.command == "inspect-fragments":
            return _run_fragment_inspection(args)
        if args.command == "visualize":
            return _run_visualization(args)
        if args.command == "track":
            return _run_tracking(args)
        # La política explícita de CLI preval sobre la configuració; si no n’hi ha, conservem els buits.
        config_policy = "report"
        if args.config:
            manifest_path, config_policy = load_inspection_config(args.config)
        else:
            manifest_path = args.manifest
        manifest = load_manifest(manifest_path)
        # Validem les rutes abans del cost de sondeig, impedint col·lisions i sobreescriptures.
        outputs = [p.resolve() for p in (args.output, args.frames_output) if p is not None]
        if len(set(outputs)) != len(outputs):
            raise InputError("Summary and frame exports must have different paths")
        protected = {manifest.path, manifest.video_path, manifest.detections_path}
        if args.config:
            protected.add(args.config.resolve())
        for path in outputs:
            if path in protected or path.exists():
                raise InputError(f"Refusing to overwrite an input or existing output: {path}")
            path.parent.mkdir(parents=True, exist_ok=True)
        # El sondeig dona temps i dimensions. La lectura OpenPose rebrà aquesta mateixa referència.
        video = probe_video(manifest.video_path, manifest.case_id, ffprobe=args.ffprobe, timeout_s=args.probe_timeout)
        # No publiquem resultats mentre s’estan llegint registres que encara podrien fallar.
        with tempfile.TemporaryDirectory(prefix="trampoline-inspect-") as temporary:
            temp = Path(temporary)
            staged_frames = temp / "frames.jsonl"
            policy = args.missing_frames_policy or config_policy
            if args.frames_output:
                with staged_frames.open("w", encoding="utf-8", newline="\n") as stream:
                    result = inspect_case(manifest, video, missing_frames_policy=policy, frames_output=stream)
            else:
                result = inspect_case(manifest, video, missing_frames_policy=policy)
            result["artifacts"] = {"frames_jsonl": str(args.frames_output.resolve()) if args.frames_output else None}
            serialized = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
            staged_summary = temp / "summary.json"
            staged_summary.write_text(serialized, encoding="utf-8")
            if args.frames_output:
                _publish(staged_frames, args.frames_output.resolve())
            # L’informe es publica al final. Els dos artefactes no es publiquen en una transacció conjunta.
            if args.output:
                _publish(staged_summary, args.output.resolve())
                print(f"Inspection complete: {args.output.resolve()}")
            else:
                sys.stdout.write(serialized)
        return 0
    # Errors esperats: missatge curt a stderr i codi 2, sense convertir-los en èxit amb dades buides.
    except (InputError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
