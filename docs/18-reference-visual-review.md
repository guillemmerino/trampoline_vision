# 18. Revisió inicial del vídeo de referència

Data: 24 d'octubre de 2026. Cas: `JPN_AGE_1_000905_31.0`.
Versió del paquet: 0.2.0. Execució local amb Docker CPU, PyAV 16.1.0 i Pillow 13.0.0.

## Artefactes generats

Els fitxers es desen a `runs/`, que no es versiona. Les comandes per reproduir-los són a la
[guia de visualització](17-visualization-guide.md). No són noves deteccions: utilitzen el ZIP existent.

| Fitxer | Tram original | Vista | Fotogrames | Durada exportada | Dimensions |
| --- | --- | --- | --- | --- | --- |
| `review-short.mp4` + `.json` | 0–3 s; índexs 0–89 | all / filtered | 90 | 3 s | 1920 × 1144 |
| `review-flight.mp4` + `.json` | 14–17 s; índexs 420–509 | all / filtered | 90 | 3 s | 1920 × 1144 |
| `review-full.mp4` + `.json` | 0–31 s; índexs 0–929 | filtered | 930 | 31 s | 960 × 1144 |

També s'han extret `review-short-frame30.jpg`, `review-flight-frame450.jpg`,
`review-full-frame150.jpg` i `review-full-samples.jpg` per facilitar la revisió d'imatges.
El mosaic del clip complet mostra índexs 0, 150, 300, 450, 750 i 929.

## Comprovacions tècniques

Han passat les 37 proves dins de Docker, incloses les anteriors d'ingestió i les noves de
píxels, preservació de dades, buits, intervals parcials, vídeo VFR i errors abans de publicar.
El nucli també s'importa sense les dependències opcionals de visualització.

ffprobe ha verificat recompte, dimensions, temps i durada dels tres artefactes. El clip complet
té error màxim de timestamps i durada de 0 s; al tram de vol la diferència màxima és d'ordre
1.8e-15 s per representació numèrica. No s'ha perdut ni duplicat cap fotograma de l'interval.
Els trams comencen a zero al MP4, mentre les capçaleres i els informes conserven temps originals.

La generació i verificació ha trigat aproximadament 8.0 s per a la mostra inicial, 14.0 s per al
tram de vol i 42.9 s per al clip complet. No inclou el sondeig inicial que fa la CLI. Són mesures
d'aquesta execució, no un benchmark ni una promesa de rendiment. Un tram avançat també llegeix
i descodifica des del principi per mantenir correspondència exacta d'índexs.

## Observacions visuals de les mostres

- La imatge original queda sota una capçalera addicional de 64 píxels, a escala 1:1. Les dues
  vistes de comparació mostren el mateix instant i el mateix desplaçament vertical.
- A les mostres revisades, molts punts coincideixen amb persones de la grada i la taula de jutges,
  però també apareixen esquelets llargs, fragments i connexions clarament poc plausibles.
- Al fotograma 30 (1 s), all dibuixa 97 deteccions i filtered 19. El filtre redueix soroll, però
  no prova que les 19 restants siguin persones correctes ni resol duplicats.
- El clip complet conserva 89.725 deteccions d'origen. La vista filtrada dibuixa 18.306 propostes
  acumulades al llarg dels fotogrames. Cap dels dos valors és un recompte de persones úniques.
- En mostres de vol el gimnasta pot quedar sense esquelet visible a filtered, mentre públic i
  jutges continuen apareixent. La comparació all permet veure que hi pot haver evidència parcial
  de baixa confiança que el filtre de dibuix amaga.

## Cas concret per al treball posterior

Al fotograma intern 450 (15 s), la vista all té 97 deteccions i filtered en conserva 16.
Les propostes `450:85` i `450:88`, visibles a la zona de l'atleta a la comparació, provenen del
JSON extern `frame_000451_keypoints.json`. La inspecció del registre mostra 5 i 3 punts observats,
respectivament, i cap punt amb confiança >= 0.25. Per això no apareixen amb el filtre inicial.

No s'afirma que aquestes propostes constitueixin un esquelet correcte ni s'assigna automàticament
identitat. El cas serveix per estudiar evidència parcial i evitar reutilitzar sense validació els
llindars visuals com a filtre previ del tracker.

## Abast de la conclusió

El pas 3 ja proporciona una eina funcional de diagnòstic visual, amb exportació temporal comprovada
i casos revisables de soroll i punts febles. Les mostres no són una anotació exhaustiva del vídeo:
els informes mantenen `pending_human_review` sobre l'alineació visual. La precisió de pose i la
identitat no s'han mesurat amb ground truth.

Continuen pendents deduplicació, seguiment, selecció del gimnasta i segmentació de salts.
La discrepància de durada 25/31 s de les metadades es conserva com a avís. TFM i les deteccions
originals s'han consumit només per a lectura.
