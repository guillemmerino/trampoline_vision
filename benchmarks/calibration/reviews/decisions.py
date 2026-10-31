"""Decisions de revisió explícites, vinculades a vídeo, referència i caixa originals."""

from benchmarks.calibration.engine.common import digest


def validate_decisions(value, cases, reference_hashes, detectors, models):
    if (set(value) != {"schema_version", "review_id", "reference_acceptance", "detector_roles", "decisions"}
            or value["schema_version"] != "1.0" or not isinstance(value["review_id"], str)
            or not isinstance(value["reference_acceptance"], list) or not isinstance(value["decisions"], list)
            or not isinstance(value["detector_roles"], dict)):
        raise ValueError("Invalid detection review decisions schema")
    if any(role not in {"primary", "control"} for role in value["detector_roles"].values()):
        raise ValueError("Detector role must be primary or control")
    accepted = set()
    for entry in value["reference_acceptance"]:
        case = entry["case_id"]
        if case in accepted:
            raise ValueError("Duplicate reference acceptance")
        accepted.add(case)
        if (case in cases and (entry["video_sha256"] != cases[case]["sha256"]
                or entry["reference_sha256"] != reference_hashes[case])):
            raise ValueError("Accepted reference differs from current input")
        if entry.get("accepted_for_study") is not True or not entry.get("reviewer") or not entry.get("notes"):
            raise ValueError("Reference acceptance needs explicit reviewer, notes and acceptance")
    seen = set()
    for entry in value["decisions"]:
        key = (entry["case_id"], entry["detector"], entry["frame_index"])
        if key in seen or type(entry["frame_index"]) is not int:
            raise ValueError("Duplicate or invalid detection decision")
        seen.add(key)
        if entry["classification"] not in {"sufficient", "partial", "absent_or_incorrect"}:
            raise ValueError("Unknown localization classification")
        if not entry.get("reviewer") or entry.get("reviewer_type") not in {"human", "model"} or not entry.get("notes"):
            raise ValueError("Detection decision requires review provenance")
        case, detector = entry["case_id"], entry["detector"]
        if case not in cases or detector not in detectors:
            continue  # Un mateix registre pot incloure altres variants històriques.
        settings = detectors[detector]
        if (entry["video_sha256"] != cases[case]["sha256"] or entry["reference_sha256"] != reference_hashes[case]
                or entry["detector_settings_sha256"] != digest(settings)
                or entry["weights_sha256"] != models[settings["model"]]["sha256"]):
            raise ValueError("Detection decision input/model/settings differ")
        if not 0 <= entry["frame_index"] < cases[case]["video"]["frame_count"]:
            raise ValueError("Detection decision frame is outside video")
    return value


def apply_localization_review(samples, boxes, decisions=()):
    """No canvia l'IoU ni les deteccions; la parcialitat només és una decisió registrada."""
    by_frame = {decision["frame_index"]: decision for decision in decisions}
    if len(by_frame) != len(decisions):
        raise ValueError("Duplicate localization decision")
    if not set(by_frame) <= {sample["frame_index"] for sample in samples}:
        raise ValueError("Decision frame is not annotated")
    for sample in samples:
        index = sample["frame_index"]
        if sample["reference_state"] != "visible":
            classification, source = "excluded", "reference_state"
        elif sample["detector_available"]:
            classification, source = "sufficient", "iou_rule"
        elif not boxes[index]:
            classification, source = "absent_or_incorrect", "no_detections"
        else:
            classification, source = "needs_review", "review_required"
        sample.update(localization_class=classification, localization_source=source,
                      partial_bbox=False, reviewed_candidate_id=None, reviewed_bbox_xyxy=None,
                      reviewed_candidate_confidence=None, localization_reviewer=None, localization_reviewer_type=None,
                      localization_notes=None)
        if index in by_frame:
            decision = by_frame[index]
            if decision["classification"] not in {"sufficient", "partial", "absent_or_incorrect"}:
                raise ValueError("Unknown localization classification")
            if classification == "excluded":
                raise ValueError("Cannot classify an excluded frame without revising the reference separately")
            candidate = decision["candidate"]
            found = [box for box in boxes[index] if box["bbox_xyxy"] == candidate["bbox_xyxy"]
                     and box["confidence"] == candidate["confidence"]]
            if len(found) != 1:
                raise ValueError("Reviewed candidate is missing, changed or ambiguous; review it again")
            sample.update(localization_class=decision["classification"], localization_source="explicit_review",
                          partial_bbox=decision["classification"] == "partial", reviewed_candidate_id=found[0]["det_id"],
                          reviewed_bbox_xyxy=found[0]["bbox_xyxy"], reviewed_candidate_confidence=found[0]["confidence"],
                          localization_reviewer=decision["reviewer"], localization_reviewer_type=decision["reviewer_type"],
                          localization_notes=decision["notes"])
        sample["association_candidate_available"] = (True if sample["localization_class"] in {"sufficient", "partial"}
                                                    else False if sample["localization_class"] == "absent_or_incorrect" else None)
    classes = [sample["localization_class"] for sample in samples]
    return {"sufficient_localization_samples": classes.count("sufficient"),
            "partial_localization_samples": classes.count("partial"),
            "absent_or_incorrect_samples": classes.count("absent_or_incorrect"),
            "needs_review_samples": classes.count("needs_review"),
            "explicitly_reviewed_samples": sum(sample["localization_source"] == "explicit_review" for sample in samples)}
