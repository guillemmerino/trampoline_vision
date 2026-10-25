"""Cache SQLite incremental de descriptors, vinculat a inputs i preprocessament exactes.

Només desa aparença, mai decisions del tracker. Canviar llindars o backend
pot reutilitzar-la; canviar pesos, píxels, caixes o context rebutja la reutilització.
"""

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sqlite3
import struct
import zlib

from trampoline_vision.contracts.appearance import CandidateEmbedding, FrameAppearance
from trampoline_vision.tracking.errors import TrackingError


def frame_signature(frame):
    """Identifica candidats i mesures reals, incloent-ne l'ordre, sense incorporar IDs temporals."""
    payload = {"context": asdict(frame.source.context), "source_status": frame.source.source_status,
               "measurements": [(c.candidate_id, asdict(c.measurement)) for c in frame.candidates if c.measurement is not None]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()


class EmbeddingCache:
    """Una connexió per execució; cada fila publicada és un fotograma d'aparença complet."""

    def __init__(self, directory, identity, model_fingerprint):
        """Obre un cache identificat pel contingut i comprova les metadades abans de llegir vectors."""
        metadata = json.dumps({"schema_version": "1.0", **identity}, sort_keys=True, allow_nan=False)
        key = hashlib.sha256(metadata.encode()).hexdigest()
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.path, self.model_fingerprint = directory / f"{key}.sqlite3", model_fingerprint
        self.connection = None
        try:
            self.connection = sqlite3.connect(self.path, timeout=30)
            with self.connection:
                self.connection.execute("CREATE TABLE IF NOT EXISTS metadata (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)")
                self.connection.execute("INSERT OR IGNORE INTO metadata VALUES (1, ?)", (metadata,))
                if self.connection.execute("SELECT value FROM metadata WHERE id=1").fetchone()[0] != metadata:
                    raise TrackingError("Appearance cache metadata does not match inputs")
                self.connection.execute("CREATE TABLE IF NOT EXISTS frames (frame INTEGER PRIMARY KEY, signature TEXT NOT NULL, ids TEXT NOT NULL, dimension INTEGER NOT NULL, vectors BLOB NOT NULL, digest TEXT NOT NULL)")
        except (OSError, sqlite3.Error, TrackingError) as exc:
            self.close()
            raise TrackingError(f"Cannot open appearance cache {self.path}: {exc}") from exc

    def get(self, frame):
        """Retorna descriptors només si candidats, context i bytes desats són exactament compatibles."""
        try:
            row = self.connection.execute("SELECT signature, ids, dimension, vectors, digest FROM frames WHERE frame=?", (frame.source.context.frame_index,)).fetchone()
            if row is None:
                return None
            signature, encoded_ids, dimension, compressed, digest = row
            if signature != frame_signature(frame) or hashlib.sha256(compressed).hexdigest() != digest:
                raise ValueError("Cache candidate signature or vector checksum differs")
            ids = json.loads(encoded_ids)
            raw = zlib.decompress(compressed)
            count = len(ids) * dimension
            if len(raw) != count * 4 or dimension < 0 or (ids and dimension == 0):
                raise ValueError("Invalid cached descriptor shape")
            values = struct.unpack(f"<{count}f", raw)
            vectors = tuple(CandidateEmbedding(cid, tuple(values[j*dimension:(j+1)*dimension])) for j, cid in enumerate(ids))
            expected = [c.candidate_id for c in frame.candidates if c.measurement is not None]
            if ids != expected:
                raise ValueError("Cached descriptor order differs")
            return FrameAppearance(frame.source.context, self.model_fingerprint, vectors)
        except (sqlite3.Error, ValueError, TypeError, zlib.error, struct.error) as exc:
            raise TrackingError(f"Invalid appearance cache frame {frame.source.context.frame_index}: {exc}") from exc

    def put(self, frame, appearance):
        """Publica un fotograma atòmicament; una carrera concurrent no pot substituir-ne els vectors."""
        expected = [c.candidate_id for c in frame.candidates if c.measurement is not None]
        if appearance.context != frame.source.context or [e.candidate_id for e in appearance.embeddings] != expected or appearance.model_fingerprint != self.model_fingerprint:
            raise TrackingError("Appearance cache write does not match its frame or model")
        dimension = len(appearance.embeddings[0].values) if appearance.embeddings else 0
        values = [value for embedding in appearance.embeddings for value in embedding.values]
        compressed = zlib.compress(struct.pack(f"<{len(values)}f", *values))
        row = (frame.source.context.frame_index, frame_signature(frame), json.dumps(expected), dimension,
               compressed, hashlib.sha256(compressed).hexdigest())
        try:
            with self.connection:
                self.connection.execute("INSERT OR IGNORE INTO frames VALUES (?, ?, ?, ?, ?, ?)", row)
                stored = self.connection.execute("SELECT frame, signature, ids, dimension, vectors, digest FROM frames WHERE frame=?", (row[0],)).fetchone()
                if tuple(stored) != row:
                    raise TrackingError("Concurrent appearance cache values disagree")
        except sqlite3.Error as exc:
            raise TrackingError(f"Cannot write appearance cache: {exc}") from exc

    def close(self):
        """Allibera la connexió sense eliminar descriptors vàlids d'una execució parcial."""
        if self.connection is not None:
            self.connection.close()
            self.connection = None


class ReadOnlyEmbeddingCache(EmbeddingCache):
    """Llegeix cache existent; no crea fitxers, taules, descriptors ni metadades."""

    def __init__(self,path,expected_identity,model_fingerprint):
        """Exigeix identitat d'inputs i model abans de reutilitzar get/signatures del cache."""
        self.path=Path(path).resolve()
        self.model_fingerprint=model_fingerprint
        self.connection=None
        try:
            wal=Path(str(self.path)+'-wal')
            if wal.exists() and wal.stat().st_size:
                raise ValueError('Use a closed checkpointed cache, not active WAL data')
            self.connection=sqlite3.connect(self.path.as_uri()+'?mode=ro&immutable=1',uri=True,timeout=30)
            row=self.connection.execute('SELECT value FROM metadata WHERE id=1').fetchone()
            if row is None:
                raise ValueError('Missing cache metadata')
            self.metadata=json.loads(row[0])
            if not isinstance(self.metadata,dict) or self.metadata.get('schema_version')!='1.0':
                raise ValueError('Unsupported cache schema')
            expected={**expected_identity,'model_fingerprint':model_fingerprint}
            if any(self.metadata.get(k)!=v for k,v in expected.items()):
                raise ValueError('Cache input/model identity differs')
        except (OSError,sqlite3.Error,ValueError,TypeError) as exc:
            self.close()
            raise TrackingError(f'Cannot open verified read-only appearance cache: {exc}') from exc
