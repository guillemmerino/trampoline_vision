"""Diagnòstic dispers sobre caixes del vídeo original, independent del detector.

No és MOT exhaustiu, ni selecció del gimnasta, ni una nota de qualitat global.
Una predicció mai no compta com observació. El matching per màxim IoU és
explícit; duplicats i ambigüitats queden comptats, sense escollir un track global.
"""

import math

from benchmarks.calibration.common import read_json


def iou(left, right):
    overlap = max(0, min(left[2], right[2]) - max(left[0], right[0])) * max(0, min(left[3], right[3]) - max(left[1], right[1]))
    area = lambda box: (box[2] - box[0]) * (box[3] - box[1])
    return overlap / (area(left) + area(right) - overlap)


def box_values(box):
    return [box[key] for key in ("x_min", "y_min", "x_max", "y_max")]


def load_reference(path, case, threshold=.5, *, allow_provisional=False):
    value = read_json(path)
    if (value.get("schema_version") != "1.0" or value.get("case_id") != case["case_id"]
            or value.get("video_sha256") != case["sha256"]):
        raise ValueError(f"Reference does not identify the same video: {path}")
    if value.get("status") == "draft":
        return None
    if value.get("status") == "provisional" and not allow_provisional:
        return None
    accepted_status = {"reviewed", "provisional"} if allow_provisional else {"reviewed"}
    if (value.get("status") not in accepted_status or not value.get("reviewer")
            or not isinstance(value.get("samples"), list) or not value["samples"]):
        raise ValueError("Reference requires an accepted review status, reviewer and samples")
    samples = {}
    for sample in value["samples"]:
        index, box, state = sample.get("frame_index"), sample.get("bbox_xyxy"), sample.get("state")
        if (type(index) is not int or not 0 <= index < case["video"]["frame_count"] or index in samples
                or state not in {"visible", "occluded", "out_of_frame", "ambiguous"}):
            raise ValueError("Invalid or duplicate reference frame")
        if state == "visible":
            if (not isinstance(box, list) or len(box) != 4 or any(type(x) not in (int, float) or not math.isfinite(x) for x in box)
                    or not 0 <= box[0] < box[2] <= case["video"]["width_px"]
                    or not 0 <= box[1] < box[3] <= case["video"]["height_px"]):
                raise ValueError("Visible target requires a valid original-pixel bbox")
        elif box is not None:
            raise ValueError("Excluded reference frames require bbox_xyxy=null")
        samples[index] = sample
    if not any(sample["state"] == "visible" for sample in samples.values()):
        raise ValueError("Reference needs at least one visible sample")
    return samples


def evaluate(frames_path, samples, threshold=.5, *, video_id=None):
    matches, visited, run_id = [], set(), None
    previous = -1
    with frames_path.open(encoding="utf-8") as stream:
        import json
        for line in stream:
            frame = json.loads(line)
            index = frame["context"]["frame_index"]
            if video_id is not None and frame["context"].get("video_id") != video_id:
                raise ValueError("Tracking trace belongs to a different video")
            if index != previous + 1 or (run_id is not None and frame["run_id"] != run_id):
                raise ValueError("Evaluation needs a continuous full-video single-run trace")
            previous, run_id = index, frame["run_id"]
            if index not in samples:
                continue
            visited.add(index)
            ref = samples[index]
            if ref["state"] != "visible":
                continue
            target = ref["bbox_xyxy"]
            candidates = {candidate["candidate_id"]: candidate for candidate in frame["candidates"]}
            available = [candidate for candidate in candidates.values() if candidate["measurement"] is not None
                         and iou(box_values(candidate["measurement"]["bbox"]), target) >= threshold]
            observed = [(iou(box_values(track["bbox"]), target), track["track_id"])
                        for track in frame["tracks"] if track["evidence"] == "observed" and track["bbox"] is not None
                        and iou(box_values(track["bbox"]), target) >= threshold]
            observed.sort(key=lambda pair: (-pair[0], pair[1]))
            matches.append({"frame_index": index, "detector_available": bool(available),
                            "matching_candidates": len(available), "matching_observed_tracks": len(observed),
                            "track_id": observed[0][1] if observed else None})
    if visited != set(samples):
        raise ValueError("Some annotated frames are missing from the trace")
    ids = [sample["track_id"] for sample in matches if sample["track_id"] is not None]
    return {"status": "evaluated_sparse", "protocol": "target_max_iou_v1", "iou_threshold": threshold,
            "visible_samples": len(matches), "excluded_samples": len(samples) - len(matches),
            "detector_available_samples": sum(sample["detector_available"] for sample in matches),
            "observed_matches": len(ids), "observed_coverage": len(ids) / len(matches),
            "distinct_matched_ids": len(set(ids)),
            "id_changes_between_reviewed_matches": sum(left != right for left, right in zip(ids, ids[1:])),
            "samples_with_duplicate_observed_matches": sum(sample["matching_observed_tracks"] > 1 for sample in matches),
            "samples": matches,
            "limitations": ["sparse_annotations_only", "max_iou_matching_can_switch_between_duplicates",
                            "not_HOTA_IDF1_MOTA", "not_actor_purity_or_automatic_subject_selection"]}
