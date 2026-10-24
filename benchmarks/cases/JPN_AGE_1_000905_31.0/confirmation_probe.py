"""Reprodueix la reconfirmació després d'un buit amb trackers 2.6.1 i el paquet 0.3.0.

No utilitza el vídeo real ni atributs privats de la biblioteca. És una prova
de diagnòstic del baseline, no una correcció del tracker ni un benchmark.
Executar al runtime de tracking amb --output apuntant a un fitxer nou.
"""

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from trampoline_vision import __version__
from trampoline_vision.contracts.observations import (
    BODY25_NAMES, DetectionProvenance, FrameContext, FrameDetections,
    KeypointObservation, PersonDetection,
)
from trampoline_vision.preparation.pipeline import prepare_frame
from trampoline_vision.tracking.config import TrackerConfig
from trampoline_vision.tracking.session import TrackingSession


def make_frame(index: int) -> FrameDetections:
    """Crea una pose immòbil de confiança 0.9, amb un únic fotograma buit a índex 6."""
    coords = {"neck": (50, 20), "right_shoulder": (40, 30), "left_shoulder": (60, 30),
              "mid_hip": (50, 60), "right_knee": (45, 80), "left_knee": (55, 80)}
    points = tuple(KeypointObservation(name, *coords[name], .9, True, True) if name in coords else
                   KeypointObservation(name, None, None, 0, False, None) for name in BODY25_NAMES)
    person = PersonDetection(str(index), points, DetectionProvenance("synthetic", "frame", index, 0, "synthetic", "unknown"))
    return FrameDetections(FrameContext("confirmation-probe", index, index / 30, 1 / 30, 100, 100),
                           () if index == 6 else (person,), "present")


def main() -> None:
    """Registra totes les sortides i comprova el cas confirmat → buit → dues associacions ocultes → recuperació."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    session = TrackingSession(TrackerConfig(confirmation_frames=3), 30)
    rows = []
    for index in range(10):
        frame = make_frame(index)
        result = session.update(prepare_frame(frame))
        rows.append({"frame_index": index, "input_detections": len(frame.detections),
                     "tracks": [asdict(t) for t in result.tracks],
                     "unassigned": list(result.unassigned_candidate_ids)})
    assert rows[5]["tracks"][0]["evidence"] == "observed"
    assert rows[6]["input_detections"] == 0
    for index in (7, 8):
        assert rows[index]["input_detections"] == 1
        assert rows[index]["tracks"][0]["evidence"] == "predicted"
        assert rows[index]["unassigned"]
    assert rows[9]["tracks"][0]["evidence"] == "observed"
    result = {"software_version": __version__, "confirmation_frames": 3,
              "diagnostic": "current association hidden during reconfirmation", "frames": rows}
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
