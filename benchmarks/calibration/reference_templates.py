"""Crea plantilles sense etiquetes inventades per revisar el gimnasta al vídeo."""

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmarks.calibration.common import inside, read_json


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--corpus", type=Path, default=Path(__file__).with_name("corpus.json"))
    cli.add_argument("--suite", default="pilot")
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args(argv)
    corpus = read_json(args.corpus)
    for case in corpus["cases"]:
        if case["case_id"] not in corpus["suites"][args.suite]:
            continue
        path = inside(args.output, case["case_id"] + ".json")
        if path.exists():
            continue  # Mai no reemplaça anotacions que algú hagi començat a revisar.
        path.parent.mkdir(parents=True, exist_ok=True)
        count = case["video"]["frame_count"]
        value = {"schema_version": "1.0", "case_id": case["case_id"], "video_sha256": case["sha256"],
                 "status": "draft", "reviewer": "", "notes": "Add dense windows at inversions/contacts; this scaffold is not ground truth.",
                 "samples": [{"frame_index": index, "state": "ambiguous", "bbox_xyxy": None}
                             for index in sorted({0, count // 4, count // 2, 3 * count // 4, count - 1})]}
        with path.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
        print(path)


if __name__ == "__main__":
    main()
