"""Verifica hashes i timeline de tot el corpus, amb descodificació opcional."""

import argparse
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from benchmarks.calibration.engine.common import atomic_json, digest, inside, read_json, verify_file


def main(argv=None):
    from trampoline_vision.ingestion.video import probe_video
    from trampoline_vision.ingestion.video_frames import VideoFrameReader
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--dataset", type=Path, required=True)
    cli.add_argument("--full-decode", action="store_true")
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args(argv)
    if args.output.exists() or args.output.resolve().is_relative_to(args.dataset.resolve()):
        cli.error("Choose a new report outside the dataset")
    corpus = read_json(args.dataset / "corpus.json")
    for model in corpus["models"]:
        verify_file(inside(args.dataset, model["path"]), model["sha256"])
    results = []
    for index, case in enumerate(corpus["cases"], 1):
        path = inside(args.dataset, case["path"])
        verify_file(path, case["sha256"])
        video = probe_video(path, case["case_id"])
        expected = case["video"]
        if (video.width_px, video.height_px, video.frame_count) != (expected["width_px"], expected["height_px"], expected["frame_count"]) or abs(video.duration_s - expected["duration_s"]) > .01:
            raise ValueError(f"Inventory/timeline mismatch: {case['case_id']}")
        if args.full_decode:
            reader = VideoFrameReader(video)
            try:
                for ordinal in range(video.frame_count):
                    reader.get(ordinal)
            finally:
                reader.close()
        results.append({"case_id": case["case_id"], "frames": video.frame_count, "duration_s": video.duration_s,
                        "video_sha256": case["sha256"], "full_decode": args.full_decode, "warnings": video.warnings})
        print(f"[{index}/{len(corpus['cases'])}] {case['case_id']}: {video.frame_count} verified frames", flush=True)
    atomic_json(args.output, {"corpus_id": corpus["corpus_id"], "corpus_sha256_canonical": digest(corpus),
                             "models_verified": len(corpus["models"]), "cases": results,
                             "total_frames": sum(item["frames"] for item in results),
                             "identity_accuracy": "not_evaluated"})


if __name__ == "__main__":
    main()
