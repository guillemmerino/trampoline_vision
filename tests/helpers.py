"""Dades sintètiques petites compartides per les proves d'ingestió.

Es creen en carpetes temporals de cada prova. No carreguen ni modifiquen
els vídeos de TFM. Les línies temporals injectades permeten provar el
lector sense FFmpeg; la prova d'integració real genera un MP4 a part.
"""

import json
from pathlib import Path
import zipfile

from trampoline_vision.contracts.observations import VideoAsset


def body25(x=10.0, y=20.0, confidence=0.8):
    """Retorna 75 valors X/Y/confiança per generar una persona BODY_25 controlada.

    Repetir un punt per a les 25 articulacions simplifica la fixture i permet
    variar només el camp que s'està provant; no pretén simular una pose real.
    """
    return [value for _ in range(25) for value in (x, y, confidence)]


def make_case(root: Path, records: dict, *, base=1, directory=False, expected=None):
    """Crea un manifest i una font JSON de prova dins de root i retorna la ruta del manifest.

    records associa noms de registre a objectes JSON o text deliberadament
    incorrecte. directory selecciona carpeta o ZIP; base i expected permeten
    provar índexs i metadades. El vídeo és un placeholder si no n'hi ha cap:
    la majoria de proves injecten una línia temporal i no el descodifiquen.
    """
    video = root / "video.mp4"
    if not video.exists():
        # Aquest fitxer només satisfà l’existència de la font; els tests amb temps injectats no el descodifiquen.
        video.write_bytes(b"placeholder for injected timeline")
    if directory:
        source = root / "poses"
        source.mkdir(exist_ok=True)
        for name, payload in records.items():
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")
    else:
        source = root / "poses.zip"
        with zipfile.ZipFile(source, "w") as archive:
            for name, payload in records.items():
                archive.writestr(name, payload if isinstance(payload, str) else json.dumps(payload))
    manifest = {
        "schema_version": "1.0", "case_id": "test-case", "path_base": "manifest_directory",
        "video": {"path": "video.mp4", "expected": expected or {}},
        "detections": {"primary": {"format": "openpose_json_directory" if directory else "openpose_json_zip",
                                    "path": source.name, "frame_index_base": base,
                                    "skeleton_schema": "openpose_body25", "coordinate_space": "original_frame_pixels",
                                    "variant": "legacy_fused", "rotation_provenance": "unknown"}},
    }
    path = root / "case.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def timeline(root: Path, count=3):
    """Construeix un vídeo sintètic de count fotogrames a 5 FPS i 100 × 80 píxels.

    Només retorna metadades i temps. No crea un MP4 i no necessita eines externes.
    """
    return VideoAsset("test-case", root / "video.mp4", 100, 80, 5.0,
                      tuple(i / 5 for i in range(count)), tuple(0.2 for _ in range(count)))
