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
