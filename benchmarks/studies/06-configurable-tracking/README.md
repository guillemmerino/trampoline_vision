# 06 — Integració de backends i ReID al paquet

Validació de la versió 0.5.0, 25 d'octubre de 2026. No és un nou benchmark
de precisió: comprova que el nou recorregut de producció conserva les
decisions estudiades al pilot 05 i pot consumir caixes sense OpenPose.

## Resultat

- **112 proves** passen al runtime Docker complet amb la wheel final instal·lada;
  `pip check` no detecta dependències incompatibles. El Dockerfile complet
  i la configuració Compose també s'han construït/validat.
- En Python 3.10 de Windows passen les **89 proves disponibles**, amb 23
  omissions explícites per dependències visuals/FFmpeg opcionals absents.
- Les **9 traces** (3 clips × OC-SORT, BoT-SORT sense ReID i amb ReID)
  coincideixen exactament: **7.560 frames comparats**, després de traduir
  només els prefixos de candidat/track canviats deliberadament a 0.5.
  Es comparen context, observacions, prediccions, IDs, esdeveniments i
  candidats no assignats. No es descarten frames difícils.
- ByteTrack consumeix els **2.520 frames** dels tres clips amb les invariants
  de partició i vida del domini. Aquest control no li atribueix una millora
  de precisió, perquè no té una traça congelada equivalent en aquest estudi.
- Els descriptors de **9 frames reals**, tres per clip, coincideixen amb
  l'estudi 05: màxim error absolut **0** en l'entorn congelat.
- El cas d'ús públic processa els **930 frames** del primer clip amb ReID
  des del cache: 930 hits i cap càrrega/inferència de xarxa.
- Una prova addicional extreu **60 descriptors** de 3 frames originals,
  genera MP4 amb PTS verificats i després reutilitza els 3 frames des del
  cache sense carregar el model.
- La CLI de la wheel final executa també el perfil d'exemple real, amb
  manifest referenciat, pesos locals i inferència de 6 frames.

`results.json` conserva l'evidència resumida i `requirements-frozen.txt`
les versions de l'entorn final. Els artefactes locals són a
`runs/tracking-integration-06/`: informe i JSONL complets del primer clip,
cache SQLite, manifests de regressió i proves curtes d'inferència/vídeo.
Els originals i el pilot 05 no s'han modificat.

La comparació de traces s'ha fet en el runtime congelat de l'estudi 05 amb
el nou codi. La wheel final també s'ha instal·lat i provat en el runtime
Docker complet nou; això distingeix regressió numèrica de compatibilitat
d'instal·lació. Les últimes comprovacions de VFR i aïllament d'IDs es cobreixen
amb proves específiques; no alteren les entrades CFR del replay.

## Reproduir

Cal disposar dels vídeos/CSV originals a TFM, dels pesos verificats i de
`runs/tracking-reid-study-05/` amb el resum, protocol, traces i NPZ originals.
L'script comprova hashes de vídeos, CSV, pesos i NPZ, versions numèriques,
offsets, dimensions i normalització abans d'importar els descriptors antics.
Aquest importador és específic de regressió i no forma part del pipeline.
El lector de producció només consumeix CSV i el cache SQLite propi.

Des de l'arrel, després de construir el servei `tracking-reid`:

```powershell
docker compose --profile reid run --rm --entrypoint python --volume "${PWD}/benchmarks:/benchmarks:ro" tracking-reid /benchmarks/studies/06-configurable-tracking/verify_integration.py --legacy runs/tracking-reid-study-05 --tfm /workspace/TFM --weights runs/reid-models/osnet_x0_25_msmt17.pt --output runs/tracking-integration-06-repeat
```

La sortida ha de ser un directori nou. L'script falla si divergeix una traça,
un descriptor, un input o el runtime fixat. No accepta diferències de versió
silencioses; per comparar amb un runtime nou cal registrar una altra validació.

La fragmentació i les transferències d'actor del pilot continuen existint.
Coherència/recuperació del gimnasta, matching de poses, segmentació i puntuació
encara no s'han implementat en aquest increment. El següent treball ha de
mesurar aquestes millores amb anotacions independents i controls sense ReID.
