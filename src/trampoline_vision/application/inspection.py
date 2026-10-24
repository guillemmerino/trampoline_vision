"""Cas d'ús del pas 2: inspeccionar observacions enregistrades i resumir-ne la lectura.

Coordina el lector amb una línia temporal ja obtinguda i acumula dades
de qualitat d'entrada. No executa tracking, deduplicació, salts o notes.
La CLI decideix les rutes i publica els fitxers; aquest mòdul pot rebre
un stream de text per exportar observacions sense conèixer HTTP o Docker.
"""

from dataclasses import asdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import TextIO
from uuid import uuid4

from trampoline_vision import __version__
from trampoline_vision.contracts.observations import SCHEMA_VERSION, VideoAsset
from trampoline_vision.ingestion.manifest import CaseManifest
from trampoline_vision.ingestion.openpose import iter_openpose_frames


def inspect_case(manifest: CaseManifest, video: VideoAsset, *, missing_frames_policy: str = "report",
                 frames_output: TextIO | None = None) -> dict:
    """Consumeix les deteccions i retorna un informe de lectura amb procedència i avisos.

    Entrades: manifest resolt, vídeo sondejat i política de registres absents.
    Si frames_output és un stream, hi escriu una línia JSON per fotograma
    en format intern. No acumula totes les poses del vídeo en una llista.

    Retorna un dict serialitzable amb ID d'execució, configuració efectiva,
    recomptes i discrepàncies. La confiança positiva compta com a observació,
    no com a pose correcta. Sempre deixa pendent la comprovació visual del
    pas 3. Els errors del lector es propaguen: un registre corrupte no es
    converteix en un resultat complet.
    """
    counts = {"frames": 0, "source_records": 0, "missing_source_records": 0,
              "empty_present_frames": 0, "detections": 0, "max_detections_per_frame": 0,
              "valid_observed_keypoints": 0, "missing_keypoints": 0, "out_of_frame_keypoints": 0}
    # L’informe limita la mostra de buits a 100 índexs; el JSONL opcional conserva tots els fotogrames.
    missing_sample = []
    for frame in iter_openpose_frames(manifest, video, missing_frames_policy=missing_frames_policy):
        counts["frames"] += 1
        if frame.source_status == "missing":
            counts["missing_source_records"] += 1
            if len(missing_sample) < 100:
                missing_sample.append(frame.context.frame_index)
        else:
            counts["source_records"] += 1
            if not frame.detections:
                counts["empty_present_frames"] += 1
        counts["detections"] += len(frame.detections)
        counts["max_detections_per_frame"] = max(counts["max_detections_per_frame"], len(frame.detections))
        for detection in frame.detections:
            for point in detection.keypoints:
                counts["valid_observed_keypoints"] += int(point.valid)
                counts["missing_keypoints"] += int(not point.valid)
                # None indica punt absent; només False compta com a observació fora de la imatge.
                counts["out_of_frame_keypoints"] += int(point.in_frame is False)
        # Serialitzem fotograma a fotograma; no carreguem totes les poses del vídeo alhora.
        if frames_output is not None:
            record = {"schema_version": SCHEMA_VERSION, **asdict(frame)}
            frames_output.write(json.dumps(record, allow_nan=False, ensure_ascii=False) + "\n")
    warnings = [{"code": w} for w in video.warnings]
    actual = {"width_px": video.width_px, "height_px": video.height_px, "fps": video.fps,
              "frame_count": video.frame_count, "duration_s": video.duration_s}
    # Una discrepància de referència genera avís; les dades reals del vídeo es mantenen.
    for key, expected in manifest.expected.items():
        value = actual[key]
        if value is None or not math.isclose(value, expected, rel_tol=1e-5, abs_tol=1e-4):
            warnings.append({"code": "expected_video_metadata_mismatch", "field": key, "expected": expected, "actual": value})
    reference_duration = manifest.declared_reference_duration_s
    if reference_duration is not None and not math.isclose(reference_duration, video.duration_s, abs_tol=1e-3):
        warnings.append({"code": "reference_duration_mismatch", "declared_s": reference_duration, "video_s": video.duration_s})
    if counts["missing_source_records"]:
        warnings.append({"code": "missing_source_records", "count": counts["missing_source_records"],
                         "frame_index_sample": missing_sample, "sample_limit": 100})
    if counts["out_of_frame_keypoints"]:
        warnings.append({"code": "out_of_frame_observations", "count": counts["out_of_frame_keypoints"]})
    # Correspondència per índex no demostra encara coincidència visual amb la persona dibuixada.
    warnings.append({"code": "visual_alignment_not_verified", "detail": "Index mapping is explicit; visual verification belongs to step 3."})
    return {
        "schema_version": SCHEMA_VERSION, "task": "inspect_recorded_detections",
        "status": "completed_with_warnings" if warnings else "completed",
        # L’execució té un ID propi, diferent del vídeo, i un instant de creació en UTC.
        "run_id": str(uuid4()), "created_at": datetime.now(timezone.utc).isoformat(),
        "software_version": __version__, "case_id": manifest.case_id,
        "inputs": {"manifest": str(manifest.path), "video": str(video.path), "detections": str(manifest.detections_path)},
        "resolved_options": {"missing_frames_policy": missing_frames_policy, "frame_index_base": manifest.frame_index_base,
                             "coordinate_space": "original_frame_pixels", "skeleton_schema": "openpose_body25",
                             "variant": manifest.variant, "rotation_provenance": manifest.rotation_provenance},
        "video": {**actual, "source_start_s": video.source_start_s,
                  "first_timestamp_s": video.timestamps_s[0], "last_timestamp_s": video.timestamps_s[-1],
                  "timeline_source": "ffprobe_presentation_timestamps"},
        "counts": counts, "warnings": warnings, "known_input_issues": list(manifest.known_issues),
        "capabilities_executed": ["video_timeline", "recorded_openpose_reading", "internal_contract_conversion"],
        "capabilities_not_executed": ["inference", "deduplication", "tracking", "subject_selection", "segmentation", "scoring", "annotated_video"],
    }
