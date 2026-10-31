"""Fitxers verificables i publicació de checkpoints del banc de proves."""

import hashlib
import json
import os
from pathlib import Path
import tempfile
from contextlib import contextmanager


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def sha256(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def inside(root, relative):
    """Els manifests portables no poden sortir de la seva arrel, tampoc amb symlinks."""
    root = Path(root).resolve()
    relative = Path(relative)
    target = (root / relative).resolve()
    if relative.is_absolute() or not target.is_relative_to(root) or target == root:
        raise ValueError(f"Path escapes bundle: {relative}")
    return target


def atomic_json(path, value):
    """Reemplaça només un checkpoint propi; els artefactes científics són per intent."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".checkpoint-", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def verify_file(path, expected):
    if not Path(path).is_file() or sha256(path) != expected:
        raise ValueError(f"Missing file or SHA-256 mismatch: {path}")


def artifacts(root, paths):
    return {Path(path).relative_to(root).as_posix(): sha256(path) for path in paths}


def verify_artifacts(root, hashes):
    if not hashes:
        raise ValueError("Completed job has no artifact checksums")
    for path, checksum in hashes.items():
        verify_file(inside(root, path), checksum)


@contextmanager
def exclusive_run(path):
    """Bloqueig del sistema operatiu: s'allibera també quan el procés és interromput."""
    with Path(path).open("a+b") as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise ValueError("Another process is already executing this run") from exc
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise ValueError("Another process is already executing this run") from exc
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)
