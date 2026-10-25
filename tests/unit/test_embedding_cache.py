"""Verifica que el cache només reutilitza aparença compatible i detecta corrupció."""

from dataclasses import replace
from contextlib import ExitStack, closing
import sqlite3
import tempfile
import unittest

from helpers_boxes import box_frame, appearance
from trampoline_vision.infrastructure.embedding_cache import EmbeddingCache
from trampoline_vision.tracking.errors import TrackingError


class EmbeddingCacheTests(unittest.TestCase):
    """Exerceix lectures, escriptures i conflictes reals sobre SQLite temporal."""

    def test_roundtrip_identity_geometry_and_concurrent_writers(self):
        """Un segon procés pot reutilitzar vectors; ni un model ni unes caixes diferents poden colar-se."""
        frame = box_frame()
        vectors = appearance(frame)
        with tempfile.TemporaryDirectory() as directory, ExitStack() as resources:
            cache = EmbeddingCache(directory, {'model': vectors.model_fingerprint}, vectors.model_fingerprint)
            resources.callback(cache.close)
            self.assertIsNone(cache.get(frame))
            cache.put(frame, vectors)
            self.assertEqual(cache.get(frame), vectors)
            second = EmbeddingCache(directory, {'model': vectors.model_fingerprint}, vectors.model_fingerprint)
            resources.callback(second.close)
            second.put(frame, vectors)
            swapped = replace(vectors, embeddings=tuple(replace(e, values=tuple(reversed(e.values))) for e in vectors.embeddings))
            with self.assertRaisesRegex(TrackingError, 'Concurrent'):
                second.put(frame, swapped)
            altered = replace(frame, candidates=tuple(reversed(frame.candidates)))
            with self.assertRaisesRegex(TrackingError, 'signature'):
                cache.get(altered)
            other = EmbeddingCache(directory, {'model': 'different'}, 'different')
            resources.callback(other.close)
            self.assertNotEqual(other.path, cache.path)
            self.assertIsNone(other.get(frame))
            with self.assertRaises(TrackingError):
                other.put(frame, vectors)

    def test_corruption_is_reported_instead_of_silently_recomputed(self):
        """Una fila malmesa falla explícitament i conserva la possibilitat d'auditar el problema."""
        frame = box_frame()
        with tempfile.TemporaryDirectory() as directory, ExitStack() as resources:
            cache = EmbeddingCache(directory, {}, 'synthetic-osnet')
            resources.callback(cache.close)
            cache.put(frame, appearance(frame))
            with closing(sqlite3.connect(cache.path)) as connection, connection:
                connection.execute("UPDATE frames SET vectors=?", (b'corrupt',))
            with self.assertRaisesRegex(TrackingError, 'checksum'):
                cache.get(frame)
