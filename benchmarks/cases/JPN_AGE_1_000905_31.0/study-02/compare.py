"""Resumeix el baseline 0.3.0 i els quatre experiments 0.4.0 sense tornar a executar vídeo.

Les mètriques són sobre àncores pilot fixes, no sobre tots els fotogrames ni
sobre exactitud anatòmica. Requereix els informes i avaluacions ja generats.
"""

import argparse
import json
from pathlib import Path


def load(path: Path) -> dict:
    """Carrega un informe existent; una execució absent o corrupta és un error, mai un zero inventat."""
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def normalized_frames(path: Path):
    """Llegeix els registres sense run_id per comparar contingut entre configuracions, no identitats entre versions."""
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            yield {key: value for key, value in json.loads(line).items() if key != "run_id"}


def compare(runs: Path) -> dict:
    """Construeix una taula per variant i tram i comprova l'efecte nul de dedup/core en aquests registres."""
    rows = []
    for variant in ("old", "fixed", "confidence005", "dedup", "partial"):
        for clip in ("baseline", "flight"):
            prefix = runs / f"tracking-{clip}-01" if variant == "old" else runs / "tracking-study-02" / f"{variant}-{clip}"
            evaluation_path = (runs / f"tracking-{clip}-evaluation-01.json" if variant == "old" else
                               runs / "tracking-study-02" / f"evaluation-{variant}-{clip}.json")
            report, evaluation = load(prefix.with_suffix(".json")), load(evaluation_path)
            gymnast, spotter = evaluation["subjects"]["gymnast"], evaluation["subjects"]["rear_spotter"]
            rows.append({
                "variant": variant, "clip": clip, "software_version": report["software_version"], "run_id": report["run_id"],
                "gymnast_matches": gymnast["observed_matches"], "gymnast_samples": gymnast["annotated_samples"],
                "gymnast_distinct_ids": len(gymnast["track_ids"]), "spotter_matches": spotter["observed_matches"],
                "spotter_samples": spotter["annotated_samples"], "spotter_distinct_ids": len(spotter["track_ids"]),
                "ids_seen_on_both_subjects": sorted(set(gymnast["track_ids"]) & set(spotter["track_ids"])),
                "totals": report["totals"], "unassigned_reasons": report["unassigned_reasons"],
                "events": report["events_in_selected_range"], "effective_config": report["effective_config"],
            })
    identical = {}
    for clip in ("baseline", "flight"):
        fixed = list(normalized_frames(runs / "tracking-study-02" / f"fixed-{clip}.frames.jsonl"))
        identical[clip] = {variant: fixed == list(normalized_frames(runs / "tracking-study-02" / f"{variant}-{clip}.frames.jsonl"))
                           for variant in ("dedup", "partial")}
    return {"schema_version": "1.0", "rows": rows, "identical_records_excluding_run_id": identical,
            "limitations": ["pilot_anchors_not_exhaustive", "single_detection_anchor_can_miss_valid_alternatives",
                            "track_id_numbers_not_comparable_between_versions", "more_observations_not_identity_accuracy"]}


def main() -> None:
    """Publica un resum nou sense sobreescriure dades ni artefactes d'altres iteracions."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.runs.resolve())
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
