"""Interfície de terminal per executar la inspecció CPU sobre un cas enregistrat.

Tradueix arguments a un cas d'ús, comprova les sortides i presenta errors.
La lectura de vídeo i OpenPose viu a ingestion; els recomptes viuen a
application. No importa backends de models. Es pot invocar des de
trampoline-vision o python -m trampoline_vision.
"""

import argparse
import json
import math
from pathlib import Path
import shutil
import sys
import tempfile

from trampoline_vision.application.inspection import inspect_case
from trampoline_vision.ingestion.errors import InputError
from trampoline_vision.ingestion.manifest import load_inspection_config, load_manifest
from trampoline_vision.ingestion.video import probe_video


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


def main(argv: list[str] | None = None) -> int:
    """Executa la CLI i retorna el codi de sortida del recorregut d'inspecció.

    argv permet injectar arguments en proves; None utilitza els de terminal.
    Resol configuració/manifest, rebutja sortides existents, sondeja el vídeo,
    llegeix deteccions en temporals i després publica els artefactes.
    Sense --output envia l'informe a stdout. Retorna 0 en completar la
    lectura amb o sense avisos i 2 per errors esperats d'entrada o sortida.
    argparse gestiona per separat l'ajuda i els errors de sintaxi d'arguments.
    """
    parser = argparse.ArgumentParser(prog="trampoline-vision", description="Inspect video + recorded OpenPose data on CPU.")
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
    args = parser.parse_args(argv)
    try:
        if not math.isfinite(args.probe_timeout) or args.probe_timeout <= 0:
            raise InputError("--probe-timeout must be positive")
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
