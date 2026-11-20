# Manifests de casos

El manifest de referència utilitza l'esquema executable 1.0. Les rutes relatives parteixen
de la seva carpeta i apunten a TFM, sense copiar-ne dades. El sufix example indica un cas
versionat i editable per a desenvolupament; no limita la seva execució.

Els altres exemples design-only de configuració no són equivalents a aquest manifest.

## Caixes independents

`JPN_AGE_1_000905_31.0.boxes.example.json` consumeix el CSV de caixes
enregistrades, amb base 0, coordenades originals i cobertura `complete_video`
declarada. `det_id` és local al frame. No hi ha esquema d’articulacions.
Veure [formats i límits](../../docs/27-configurable-box-tracking.md).

`JPN_AGE_1_000905_31.0.calibrated-boxes.example.json` és l’entrada actual de
`configs/pipelines/track-boxes.json`. Apunta al vídeo portable de
`data/calibration-v1` i al CSV complet enregistrat a
`runs/calibration/expanded-localization-v1`: YOLOv8m, confiança 0,001,
NMS 0,7, imgsz 1280, resize 1,5 i màxim 300 deteccions per frame.
`detector.json`, al costat del CSV, conserva configuració, SHA-256 del vídeo
i dels pesos i recursos de la inferència. Aquestes dades són locals i no
s’inclouen al repositori; el carregador falla si falten, sense usar el legacy
com a substitució implícita.
