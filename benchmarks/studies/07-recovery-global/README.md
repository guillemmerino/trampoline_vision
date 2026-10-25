# 07 — Recovery global experimental i registre de perfils

25/10/2026. **No és un benchmark de recovery fiable.** La versió 0.7.0
integra propostes auditables; no activa apply ni canvia detector/tracker.

## Registre

- `experiments.json`: perfils, receptes, hashes i ubicacions dels pilots.
- `pilot-results.json`: resum numèric de les proves realment executades.
- `import_full_audit.py`: adaptador explícit i verificat del pilot extern
  JSONL/NPZ a traça canònica/cache SQLite, sense repetir inferència.
- `integration-results.json`: verificació del paquet integrat; és una prova
  de comportament/procedència, no una nova avaluació independent de precisió.

Els originals grans (vídeo, traces, descriptors, comparatives, imatges) són
a la carpeta germana `TFM/audits/`. Els manifests preservats al registre
identifiquen els bytes i els scripts utilitzats. No es mouen ni es modifiquen.
Els perfils executables integrats poden tenir petites diferències numèriques
respecte del pilot NumPy (resums de doble precisió, timestamps reals); es
registra explícitament la regressió sobre les dades congelades, no s'assumeix.

## Experiments fets

1. Tres vídeos històrics complets, 2.520 frames: abaixar confiança forta
   .10 → .05 millora coincidències escasses 126/151 → 134/151, però IDs
   190 → 327 i fragments 1.097 → 1.958. No és una millora sòlida de continuïtat.
2. Finestra nova 430–529: proves de detector .05/.02/.01, amb/sense top20.
   El tracker arrencava al frame 430. El bon resultat local no demostrava
   continuïtat des del principi del vídeo.
3. Vídeo nou complet de 930 frames, des de zero, amb mateix BoT-SORT/ReID:

| Detector | Coincidències revisades | Canvis mínims d'ID | Fragments de tots els actors |
| --- | --- | --- | --- |
| .05, top20 per àrea | 79/85 | 7 | 498 |
| .05, sense tall per àrea | 79/85 | 8 | 193 |
| .02, sense tall per àrea | 79/85 | 9 | 156 |

4. Associació global offline, nou configuracions sobre aquestes mateixes
   traces i descriptors. Prova principal .02: canvis mínims 9 → 5, mateixa
   cobertura de 79/85, quatre cadenes principals del gimnasta. S'observen
   retrobaments correctes `1 → 56 → 61` i `93 → 106 → 112`.
   La cadena amb més coincidències de la prova principal en té 31 davant 45
   del millor track original: reduir canvis no demostra tota la continuïtat.
   La variant conservadora reuneix 53 instants, però manté almenys 6 canvis.
   Amb horitzó de 31 s no hi ha millora dels canvis (9 → 9).

Les referències són escasses, assistides i no independents del treball anterior.
Hi ha caixes mixtes i una referència que inclou un jutge al frame 885. No són
ground truth dens ni permeten HOTA/IDF1. La revisió visual addicional tampoc
és una validació humana independent. Els costos no utilitzen aquestes etiquetes.

## Reproduir sense reexecutar models

Amb el paquet 0.7.0 instal·lat, NumPy per a l'import i FFprobe disponible,
des de l'arrel del projecte:

```text
python benchmarks/studies/07-recovery-global/import_full_audit.py --audit-root ../TFM/audits/detector-confidence-full-20261025 --video ../TFM/jumping_score/output_clips/JPN_AGE_1_000905_31.0.mp4 --variant conf002_all --output runs/recovery-import-07
```

L'import exigeix una carpeta nova. Comprova vídeo, hashes, contextos, candidats,
offsets, dimensions, normalització i fingerprint. L'únic camp retirat de la
traça és `source_frame_index` redundant, després de comprovar-lo; cap decisió
del tracker no es modifica. Exporta les caixes seleccionades a CSV i registra
la transformació/procedència. L'informe d'import identifica el fitxer SQLite.

```text
python -m trampoline_vision audit-recovery --tracking-report runs/recovery-import-07/tracking.json --config configs/experiments/recovery/global-osnet-hungarian-v1.json --appearance-cache runs/recovery-import-07/cache/HASH.sqlite3 --output runs/recovery-audit-07.json
```

Substituir `HASH.sqlite3` per la ruta retornada per l'importador; no és un nom
fix. Comparar disabled/geometria/aparença sobre **el mateix tracking**.
Per estudiar detector/tracker, fer experiments separats i conservar també
els perfils i les deteccions corresponents. No barrejar canvis de detector
i associació per atribuir una millora a l'algorisme.

La [guia 30](../../../docs/30-experimental-recovery-audit.md) descriu els camps,
els controls, les garanties implementades i els límits pendents.
