# Pipelines

`inspect-openpose.json` executa el pas 2 i `visualize-openpose.json` la revisió visual del pas 3. `replay-openpose.example.json` continua
com a disseny del recorregut complet. `track-openpose.json` ja executa preparació,
OC-SORT i registre d'identitats. La segmentació continua pendent.

Vegeu [execució CPU](../../docs/15-cpu-replay-guide.md).
Per seguiment, artefactes i anotacions: [guia 21](../../docs/21-tracking-validation-guide.md).

## Preparació de caixes en el pipeline de tracking

| Configuració | Caixes que rep el tracker |
| --- | --- |
| Sense preparation_config | Una candidata per detecció enregistrada, en l’ordre original. |
| Perfil box-candidates.json | Agrupament conservador de caixes molt semblants i avisos de contenció. |
| Perfil representative-boxes.json | Zona, fons fix, rànquing per silueta i fins a 12 candidates actives. |

La comanda track demana un fitxer de pipeline explícit. Per usar el perfil
de silueta, declara preparation_config en aquell fitxer. La ruta és
relativa al pipeline. `track-boxes.json` ja activa `representative-boxes.json`
amb zona comuna centrada `[0.06, 0.25, 0.94, 0.93]`, mode `soft` i límit de 12.
El seu manifest calibrat consumeix YOLOv8m a 0,001 amb NMS 0,7, preservant
l’exemple legacy en un manifest separat. La zona és la mateixa per a tots els
clips; pressuposa el trampolí centrat i s’ha contrastat en una
[comparació aparellada de 18 clips](../../benchmarks/calibration/archive/detection-preparation-v1/docs/ZONE_COMPARISON.md).
Aquesta prova no acredita generalització a altres escenaris.
Les passes del banc seleccionen les variants via el seu pla experimental.
[Configuració i exemples](../../src/trampoline_vision/preparation/README.md).

La ruta local del model OSNet apunta també al paquet `data/calibration-v1/models`;
el SHA-256 i els paràmetres del model es mantenen. Aquesta dependència del pipeline
no intervé en `review-boxes`, que funciona sense carregar models d’aparença.
