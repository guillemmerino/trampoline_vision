# Pipelines

`inspect-openpose.json` executa el pas 2 i `visualize-openpose.json` la revisió visual del pas 3. `replay-openpose.example.json` continua
com a disseny del recorregut complet. `track-openpose.json` ja executa preparació,
OC-SORT i registre d'identitats. La segmentació continua pendent.

Vegeu [execució CPU](../../docs/15-cpu-replay-guide.md).
Per seguiment, artefactes i anotacions: [guia 21](../../docs/21-tracking-validation-guide.md).

## Preparació de caixes en el pipeline de tracking

| Configuració | Caixes que rep el tracker |
| --- | --- |
| Sense preparation_config, com al pipeline track-boxes.json | Una candidata per detecció enregistrada, en l’ordre original. |
| Perfil box-candidates.json | Agrupament conservador de caixes molt semblants i avisos de contenció. |
| Perfil representative-boxes.json | Zona, fons fix, rànquing per silueta i fins a 12 candidates actives. |

La comanda track demana un fitxer de pipeline explícit. Per usar el perfil
de silueta, declara preparation_config en aquell fitxer. La ruta és
relativa al pipeline. Revisa que la zona del perfil correspongui al vídeo.
Les passes del banc seleccionen les variants via el seu pla experimental.
[Configuració i exemples](../../src/trampoline_vision/preparation/README.md).
