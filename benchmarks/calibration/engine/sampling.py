"""Vincula una selecció de fotogrames i particions a les referències congelades."""


def validate_sampling(value, cases, references):
    if value.get("schema_version") != "1.0" or not value.get("sample_id"):
        raise ValueError("Expected sampling schema 1.0 and sample_id")
    entries = value.get("cases", [])
    if len(entries) != len(cases) or {e["case_id"] for e in entries} != set(cases):
        raise ValueError("Sampling cases must match the iteration exactly")
    for entry in entries:
        cid = entry["case_id"]
        if entry.get("video_sha256") != cases[cid]["sha256"]:
            raise ValueError("Sampling video SHA differs")
        if entry.get("partition") not in {"development", "reserved"}:
            raise ValueError("Sampling needs an explicit development/reserved partition")
        frames = entry["frames"]
        if (any(type(i) is not int for i in frames) or frames != sorted(set(frames))
                or set(frames) != set(references[cid])):
            raise ValueError("Sampling frames differ from the accepted reference")
        strata = []
        for key in ("uniform_frames", "legacy_frames", "dense_frames"):
            indices = entry.get(key, [])
            if (not isinstance(indices, list) or any(type(i) is not int for i in indices)
                    or indices != sorted(set(indices))):
                raise ValueError("Sampling strata must contain sorted unique integer frames")
            strata.append(set(indices))
        if set.union(*strata) != set(frames):
            raise ValueError("Sampling strata must cover exactly the annotated frames")
    return value


def grouped_coverage(rows):
    """Les finestres triades no es barregen amb les àncores regulars per resumir cobertura."""
    groups = {}
    for row in rows:
        for stratum in ("all_selected", *row.get("sampling_strata", [])):
            key = (row.get("partition", "unspecified"), row["detector"], stratum)
            group = groups.setdefault(key, {"partition": key[0], "detector": key[1], "stratum": stratum,
                                           "samples": 0, "visible_samples": 0, "excluded_samples": 0,
                                           "detector_available_samples": 0, "sufficient": 0, "partial": 0,
                                           "absent_or_incorrect": 0, "needs_review": 0})
            group["samples"] += 1
            if row["reference_state"] != "visible":
                group["excluded_samples"] += 1
                continue
            group["visible_samples"] += 1
            group["detector_available_samples"] += bool(row["detector_available"])
            group[row["localization_class"]] += 1
    return [groups[key] for key in sorted(groups)]
