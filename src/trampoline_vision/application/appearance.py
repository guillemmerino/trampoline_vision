"""Orquestra píxels originals, extracció d'aparença i cache, sense decidir identitats."""

from dataclasses import asdict
import hashlib
import json

from trampoline_vision.infrastructure.embedding_cache import EmbeddingCache
from trampoline_vision.ingestion.video_frames import VideoFrameReader, validate_decoded
from trampoline_vision.perception.appearance.osnet import OSNetExtractor, file_sha256


class AppearanceService:
    """Servei per vídeo, mandrós i compartit amb el descodificador de visualització."""

    def __init__(self, config, video, manifest, preparation):
        """Valida model i cache abans de començar; encara no executa la xarxa ni descodifica."""
        self.extractor = OSNetExtractor(config)
        self.video, self.reader, self.cache = video, VideoFrameReader(video), None
        self.supplied, self.supplied_index = None, -1
        self.hits = self.misses = self.extracted_candidates = 0
        if config.cache_dir:
            identity = {"video_id": video.video_id, "video_sha256": file_sha256(video.path),
                        "detections_sha256": file_sha256(manifest.detections_path),
                        "source_format": manifest.detections_format, "frame_coverage": manifest.frame_coverage,
                        "frame_index_base": manifest.frame_index_base,
                        "preparation": asdict(preparation) if manifest.detections_format != "person_boxes_csv" else None,
                        "model_fingerprint": self.extractor.fingerprint,
                        "timeline_sha256": hashlib.sha256(json.dumps([video.timestamps_s, video.frame_durations_s]).encode()).hexdigest()}
            self.cache = EmbeddingCache(config.cache_dir, identity, self.extractor.fingerprint)

    def supply_decoded(self, index, decoded):
        """Rep el mateix fotograma que codificarà l'overlay i evita una segona descodificació."""
        validate_decoded(self.video, index, decoded)
        self.supplied_index, self.supplied = index, decoded

    def for_frame(self, frame):
        """Reutilitza descriptors verificats o extreu només el fotograma que falta al cache."""
        cached = self.cache.get(frame) if self.cache else None
        if cached is not None:
            self.hits += 1
            return cached
        candidates = [c for c in frame.candidates if c.measurement is not None]
        image = None
        if candidates:
            index = frame.source.context.frame_index
            decoded = self.supplied if self.supplied_index == index else self.reader.get(index)
            image = decoded.to_ndarray(format="bgr24")
        result = self.extractor.extract(frame, image)
        self.misses += 1
        self.extracted_candidates += len(candidates)
        if self.cache:
            self.cache.put(frame, result)
        return result

    def describe(self):
        """Retorna cost d'inferència real i reutilització, distingint-los del simple model habilitat."""
        return {**self.extractor.describe(), "cache_path": str(self.cache.path) if self.cache else None,
                "cache_hit_frames": self.hits, "cache_miss_frames": self.misses,
                "extracted_candidates": self.extracted_candidates}

    def close(self):
        """Tanca recursos també quan el lector, el tracker o l'exportació fallen."""
        self.reader.close()
        if self.cache:
            self.cache.close()
