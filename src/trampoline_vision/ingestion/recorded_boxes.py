"""Lectura seqüencial de caixes de persona enregistrades, independent de pose i detector.

La cobertura de fotogrames buits és una declaració explícita del manifest:
complete_video significa detecció negativa; listed_frames_only significa
registre absent. No s'infereix completitud d'un CSV que no pot expressar buits.
"""

import csv

from trampoline_vision.contracts.geometry import BoundingBox
from trampoline_vision.contracts.observations import DetectionProvenance, FrameDetections, PersonBoxDetection
from trampoline_vision.ingestion.errors import InputError


FIELDS = {"frame", "det_id", "x1", "y1", "x2", "y2", "conf", "class_id"}


def _rows(stream, manifest, video):
    """Valida capçalera, ordre, geometria i rang temporal; conserva fila i índexs originals."""
    reader = csv.DictReader(stream)
    if reader.fieldnames is None or set(reader.fieldnames) != FIELDS or len(reader.fieldnames) != len(FIELDS):
        raise ValueError("Box CSV requires frame,det_id,x1,y1,x2,y2,conf,class_id exactly")
    previous = -1
    for row in reader:
        if set(row) != FIELDS or any(value is None for value in row.values()):
            raise ValueError(f"Invalid CSV columns at line {reader.line_num}")
        external, det_id, class_id = int(row["frame"]), int(row["det_id"]), int(row["class_id"])
        index = external - manifest.frame_index_base
        if index < previous or not 0 <= index < video.frame_count or det_id < 0:
            raise ValueError(f"Unordered or invalid frame/detection at line {reader.line_num}")
        previous = index
        box = BoundingBox(*(float(row[key]) for key in ("x1", "y1", "x2", "y2")))
        if box.x_min < 0 or box.y_min < 0 or box.x_max > video.width_px or box.y_max > video.height_px:
            raise ValueError(f"Recorded box outside original video at line {reader.line_num}")
        provenance = DetectionProvenance(str(manifest.detections_path), f"csv_line:{reader.line_num}",
                                         external, det_id, manifest.variant, manifest.rotation_provenance)
        yield index, PersonBoxDetection(f"{index}:box:{det_id}", box, float(row["conf"]), provenance, class_id)


def iter_box_frames(manifest, video, *, missing_frames_policy="report"):
    """Produeix un instant per fotograma, amb confiança i caixes originals sense articulacions artificials."""
    if manifest.detections_format != "person_boxes_csv":
        raise InputError("Box reader requires a person_boxes_csv manifest")
    if missing_frames_policy not in ("report", "error"):
        raise InputError("Unknown missing frame policy")
    try:
        with manifest.detections_path.open(encoding="utf-8-sig", newline="") as stream:
            rows = iter(_rows(stream, manifest, video))
            current = next(rows, None)
            for index in range(video.frame_count):
                detections, ids = [], set()
                while current is not None and current[0] == index:
                    detection = current[1]
                    if detection.detection_id in ids:
                        raise ValueError(f"Duplicate box detection at frame {index}")
                    ids.add(detection.detection_id)
                    detections.append(detection)
                    current = next(rows, None)
                present = bool(detections) or manifest.frame_coverage == "complete_video"
                if not present and missing_frames_policy == "error":
                    raise ValueError(f"Missing recorded boxes for frame {index}")
                yield FrameDetections(video.frame(index), tuple(sorted(detections, key=lambda d: d.provenance.source_person_index)),
                                      "present" if present else "missing")
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        raise InputError(f"Invalid box CSV {manifest.detections_path}: {exc}") from exc
