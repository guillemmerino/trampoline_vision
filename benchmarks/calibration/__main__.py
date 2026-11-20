"""Single command entry point for calibration; no command starts implicitly."""

import argparse
from importlib import import_module
import os
from pathlib import Path

COMMANDS = {
    "review": ("reviews.human", "Obrir i valorar les anotacions i YOLO; serve / assess / prepare"),
    "iterate": ("engine.iterate", "Executar o revisar un pla explícit d’iteració"),
    "run": ("engine.run", "Executor avançat de detector i trackers"),
    "report": ("reviews.tracking_report", "Reconstruir un informe de tracking"),
    "prepare": ("tools.prepare_data", "Preparar el paquet portable de dades"),
    "prepare-boxes": ("tools.prepare_boxes", "Preparar i mesurar deteccions desades sense executar tracking"),
    "verify": ("tools.verify_corpus", "Verificar els inputs del paquet"),
}
ANNOTATION_TOOLS = {
    "extract": "tools.extract_frames", "render": "tools.render_references",
    "compare": "tools.compare_references", "videos": "tools.render_videos",
    "templates": "tools.reference_templates",
}
STUDIES = {
    "representative-tracking": "run-representative-tracking.sh",
    "expanded": "run-expanded-localization.sh", "low-thresholds": "run-low-thresholds.sh",
    "thresholds": "run-iteration.sh", "localization": "run-localization.sh",
}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python3 -m benchmarks.calibration", description="Banc de calibratge. Comença pel README.md; cap prova s’executa per defecte.")
    sub = parser.add_subparsers(dest="command")
    for name, (_, help_text) in COMMANDS.items():
        sub.add_parser(name, help=help_text, add_help=False)
    annotations = sub.add_parser("annotations", help="Extreure, dibuixar o comparar referències")
    operations = annotations.add_subparsers(dest="operation", required=True)
    for name in ANNOTATION_TOOLS:
        operations.add_parser(name, add_help=False)
    study = sub.add_parser("study", help="Executar una prova acotada al servidor Docker/NVIDIA")
    study.add_argument("name", choices=STUDIES)
    args, remaining = parser.parse_known_args(argv)
    if args.command is None:
        if remaining:
            parser.error("Arguments without a command")
        parser.print_help()
        return 0
    if args.command == "study":
        script = Path(__file__).resolve().parent / "commands" / STUDIES[args.name]
        os.execvp("bash", ["bash", str(script), *remaining])
    module = ANNOTATION_TOOLS[args.operation] if args.command == "annotations" else COMMANDS[args.command][0]
    result = import_module("." + module, __package__).main(remaining)
    return result if isinstance(result, int) else 0


if __name__ == "__main__":
    raise SystemExit(main())
