# Adaptadors i utilitats del banc

Les eines coordinen inputs i artefactes. La lògica reutilitzable de preparació
continua a `src/trampoline_vision/preparation`; no s’ha de tornar a implementar aquí.

| Grup | Mòduls | Responsabilitat |
| --- | --- | --- |
| Dades | `prepare_data.py`, `verify_corpus.py` | Construir i verificar el paquet portable. |
| Anotacions | `extract_frames.py`, `reference_templates.py` | Extreure mostres i preparar referències. |
| Revisió de referències | `render_references.py`, `compare_references.py`, `render_videos.py` | Dibuixar i contrastar anotacions, sense convertir-les en veritat humana. |
| Preparació actual | `prepare_boxes.py`, `review_representative.py` | Consumir els contractes de producció i exportar una revisió independent. |
| Comparació tancada | `compare_zones.py` | Reproduir la comparació antiga hard/soft i central soft. |
| Replay històric | `representative_tracking.py` | Reproduir el protocol de 12 clips amb ByteTrack. |

Consulta el [catàleg de comandes](../commands/README.md). Les captures de
scripts dins d’`annotations/*/provenance/` són procedència històrica,
no entrades alternatives d’aquestes eines.

## Comparació temporal d’identitat

`identity_comparison.py` exigeix CSV congelats, comprova el protocol sense
tracking per defecte i orquestra quatre perfils amb `--execute`.
[Protocol i revisió independent](../config/studies/identity-continuity-v1.md).

