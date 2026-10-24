"""Diagnòstic de tracking amb anotacions manuals disperses, sense afirmar mètriques MOT completes.

Cada anotació vincula una persona real amb una detecció original en un
fotograma revisat. Això permet comparar configuracions i detectar canvis
d'ID sobre els punts revisats; no extrapola precisió a tot el vídeo.
"""

from collections import defaultdict
import math
from pathlib import Path

from trampoline_vision.ingestion.json_io import parse_json, read_json
from trampoline_vision.tracking.errors import TrackingError


def evaluate_tracking(tracks_path: Path, annotations_path: Path) -> dict:
    """Llegeix el JSONL en streaming i avalua només els instants i subjectes anotats.

    source_detection_id=null expressa persona visible però sense proposta
    identificable; compta com absència observada, mai com a èxit predit.
    Un ID diferent entre dos matches anotats del mateix subjecte és un canvi
    observat, també si hi ha anotacions no associades entremig.
    """
    annotations = read_json(annotations_path)
    if (set(annotations) - {"schema_version", "video_id", "samples"}
            or annotations.get("schema_version") != "1.0"
            or not isinstance(annotations.get("video_id"), str) or not annotations["video_id"].strip()
            or not isinstance(annotations.get("samples"), list) or not annotations["samples"]):
        raise TrackingError("Expected annotation schema 1.0, video_id and non-empty samples")
    by_frame = defaultdict(list)
    keys, sources = set(), set()
    for item in annotations["samples"]:
        if not isinstance(item, dict) or set(item) != {"frame_index", "subject_id", "source_detection_id"}:
            raise TrackingError("Each annotation requires frame_index, subject_id and source_detection_id")
        index, subject, ref = item["frame_index"], item["subject_id"], item["source_detection_id"]
        if (type(index) is not int or index < 0 or not isinstance(subject, str) or not subject.strip()
                or (ref is not None and (not isinstance(ref, str) or not ref.strip()))):
            raise TrackingError("Invalid annotation values")
        if (index, subject) in keys or (ref is not None and (index, ref) in sources):
            raise TrackingError("Duplicate subject or detection in annotations")
        keys.add((index, subject))
        if ref is not None:
            sources.add((index, ref))
        by_frame[index].append(item)
    matches, visited = [], set()
    previous_index, previous_time, run_id = None, None, None
    with tracks_path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            record = parse_json(line, f"{tracks_path}:{line_number}")
            try:
                context = record["context"]
                index, timestamp = context["frame_index"], context["timestamp_s"]
                if (record["schema_version"] != "1.0" or context["video_id"] != annotations["video_id"]
                        or type(index) is not int or index < 0
                        or isinstance(timestamp, bool) or not isinstance(timestamp, (int, float))
                        or not math.isfinite(timestamp) or timestamp < 0
                        or not isinstance(record["run_id"], str) or not record["run_id"]
                        or (previous_index is not None and (index != previous_index + 1 or timestamp <= previous_time))
                        or (run_id is not None and run_id != record["run_id"])):
                    raise ValueError("Mixed runs, invalid context or discontinuous frame sequence")
                previous_index, previous_time, run_id = index, timestamp, record["run_id"]
                candidates = {c["candidate_id"]: c for c in record["candidates"]}
                if len(candidates) != len(record["candidates"]):
                    raise ValueError("Duplicate candidates")
                for cid, candidate in candidates.items():
                    refs = candidate["source_detection_ids"]
                    if (not isinstance(cid, str) or not cid or not isinstance(refs, list) or not refs
                            or any(not isinstance(ref, str) or not ref for ref in refs)):
                        raise ValueError("Invalid candidate references")
                all_refs = [ref for c in candidates.values() for ref in c["source_detection_ids"]]
                track_ids = [t["track_id"] for t in record["tracks"]]
                assigned = [t["candidate_id"] for t in record["tracks"] if t["evidence"] == "observed"]
                if (len(set(all_refs)) != len(all_refs) or len(set(track_ids)) != len(track_ids)
                        or len(set(assigned)) != len(assigned) or not set(assigned) <= set(candidates)):
                    raise ValueError("Ambiguous source or track assignments")
                unassigned = record["unassigned_candidate_ids"]
                if (not isinstance(unassigned, list) or len(set(unassigned)) != len(unassigned)
                        or set(assigned) & set(unassigned) or set(assigned) | set(unassigned) != set(candidates)):
                    raise ValueError("Invalid assignment partition")
                mapping = {}
                for track in record["tracks"]:
                    if (not isinstance(track["track_id"], str) or not track["track_id"]
                            or track["evidence"] not in ("observed", "predicted")
                            or track["state"] not in ("active", "tentative", "lost", "finished")
                            or (track["evidence"] == "predicted" and track["candidate_id"] is not None)
                            or (track["evidence"] == "observed" and track["state"] not in ("active", "tentative"))):
                        raise ValueError("Invalid track evidence")
                    if track["evidence"] == "observed":
                        if candidates[track["candidate_id"]]["measurement"] is None:
                            raise ValueError("Observed track has no measurement")
                        for ref in candidates[track["candidate_id"]]["source_detection_ids"]:
                            mapping[ref] = track["track_id"]
                if index in by_frame:
                    visited.add(index)
                    for annotation in by_frame[index]:
                        ref = annotation["source_detection_id"]
                        if ref is not None and ref not in all_refs:
                            raise ValueError(f"Annotation references unknown detection {ref} at frame {index}")
                        matches.append({**annotation, "track_id": mapping.get(ref)})
            except (KeyError, TypeError, ValueError) as exc:
                raise TrackingError(f"Invalid tracking export or annotations at line {line_number}: {exc}") from exc
    if visited != set(by_frame):
        raise TrackingError(f"Annotated frames outside tracking export: {sorted(set(by_frame) - visited)}")
    subjects, previous_match = {}, {}
    changes, collisions = [], []
    simultaneous = defaultdict(list)
    for item in matches:
        subject, track_id = item["subject_id"], item["track_id"]
        summary = subjects.setdefault(subject, {"annotated_samples": 0, "observed_matches": 0, "track_ids": set()})
        summary["annotated_samples"] += 1
        if track_id is not None:
            summary["observed_matches"] += 1
            summary["track_ids"].add(track_id)
            before = previous_match.get(subject)
            if before and before["track_id"] != track_id:
                changes.append({"subject_id": subject, "previous_frame": before["frame_index"],
                                "frame_index": item["frame_index"], "from": before["track_id"], "to": track_id})
            previous_match[subject] = item
            simultaneous[(item["frame_index"], track_id)].append(subject)
    for (index, track_id), names in simultaneous.items():
        if len(names) > 1:
            collisions.append({"frame_index": index, "track_id": track_id, "subject_ids": names})
    for summary in subjects.values():
        summary["track_ids"] = sorted(summary["track_ids"])
    matched = sum(s["observed_matches"] for s in subjects.values())
    return {"schema_version": "1.0", "task": "evaluate_sparse_tracking_annotations", "run_id": run_id,
            "video_id": annotations["video_id"], "tracks_path": str(tracks_path.resolve()),
            "annotations_path": str(annotations_path.resolve()), "annotated_samples": len(matches),
            "observed_matches": matched, "unmatched_samples": len(matches) - matched,
            "observed_coverage_on_annotations": matched / len(matches),
            "observed_id_changes": changes, "merged_subjects": collisions, "subjects": subjects,
            "samples": matches, "limitations": ["sparse_annotations_only", "predictions_do_not_count_as_observations",
                                                   "not_HOTA_IDF1_or_MOTA", "source_detection_ids_require_same_input"]}
