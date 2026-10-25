"""Copia només els inputs congelats, sense modificar TFM ni descarregar models."""

import argparse
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmarks.calibration.common import inside, read_json, sha256, verify_file


HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]


def prepare(corpus_path, tfm_root, destination, archive=None):
    corpus_path, destination = Path(corpus_path).resolve(), Path(destination).resolve()
    corpus = read_json(corpus_path)
    if corpus.get("schema_version") != "1.0":
        raise ValueError("Expected corpus schema 1.0")
    sources = {"tfm": Path(tfm_root).resolve(), "project": PROJECT}
    if any(destination == root or destination.is_relative_to(root) for root in sources.values() if root != PROJECT):
        raise ValueError("The copy must stay outside TFM")
    entries = corpus["cases"] + corpus["models"]
    paths = [entry["path"] for entry in entries]
    if len(set(paths)) != len(paths) or "corpus.json" in paths:
        raise ValueError("Duplicate or reserved bundle paths")
    # Validació completa abans de copiar; també valida còpies parcials d'un intent anterior.
    for entry in entries:
        source = inside(sources[entry["source"]["root"]], entry["source"]["path"])
        target = inside(destination, entry["path"])
        verify_file(source, entry["sha256"])
        if target.exists():
            verify_file(target, entry["sha256"])
    snapshot = destination / "corpus.json"
    if snapshot.exists():
        verify_file(snapshot, sha256(corpus_path))
    for index, entry in enumerate(entries, 1):
        source = inside(sources[entry["source"]["root"]], entry["source"]["path"])
        target = inside(destination, entry["path"])
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as output, source.open("rb") as stream:
                shutil.copyfileobj(stream, output)
        verify_file(target, entry["sha256"])
        print(f"[{index}/{len(entries)}] verified {entry['path']}", flush=True)
    if not snapshot.exists():
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        with snapshot.open("xb") as output, corpus_path.open("rb") as stream:
            shutil.copyfileobj(stream, output)
    if archive:
        archive = Path(archive).resolve()
        if archive.exists() or Path(str(archive) + ".sha256").exists():
            raise ValueError(f"Archive already exists: {archive}")
        if archive.is_relative_to(destination):
            raise ValueError("Archive must stay outside the bundle")
        archive.parent.mkdir(parents=True, exist_ok=True)
        # No compressió: els MP4 i checkpoints ja són compactes; tar és portable.
        with tempfile.TemporaryDirectory(dir=archive.parent) as temporary:
            staged = Path(temporary) / "bundle.tar"
            with tarfile.open(staged, "w") as output:
                for relative in ["corpus.json", *paths]:
                    output.add(inside(destination, relative), arcname=relative, recursive=False)
            # Publicació exclusiva; no reemplaça cap arxiu anterior.
            with archive.open("xb") as output, staged.open("rb") as stream:
                shutil.copyfileobj(stream, output)
        checksum = sha256(archive)
        with Path(str(archive) + ".sha256").open("x", encoding="utf-8") as stream:
            stream.write(f"{checksum}  {archive.name}\n")
        print(f"Archive: {archive} ({archive.stat().st_size} bytes) SHA-256 {checksum}")
    return corpus


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=HERE / "corpus.json")
    parser.add_argument("--tfm-root", type=Path, default=PROJECT.parent / "TFM")
    parser.add_argument("--destination", type=Path, default=PROJECT / "data/calibration-v1")
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args(argv)
    try:
        prepare(args.corpus, args.tfm_root, args.destination, args.archive)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"Preparation failed: {exc}\n")


if __name__ == "__main__":
    main()
