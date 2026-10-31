# Anotacions i mostreig

| Carpeta | Contingut |
| --- | --- |
| [pilot-v1/](pilot-v1/README.md) | 72 fotogrames dels tres vídeos inicials. |
| [expanded-v1/](expanded-v1/README.md) | 1.440 fotogrames de 18 vídeos, amb particions i estrats de mostreig. |

`references/` conserva les caixes originals i els estats del gimnasta.
`selection.json` defineix els instants seleccionats. Els registres de procedència
expliquen com es van generar; no són noves comandes d’execució.

Les anotacions d’IA estan acceptades com a referència de l’estudi i mantenen
la condició de provisionals. **Les correccions humanes es desen a `runs/`,
separades dels originals**; no s’editen aquests JSON mentre es revisa l’HTML.

Revisió actual: `runs/calibration/expanded-localization-v1/human-review/`.
[Com revisar i recalcular](../docs/HUMAN_REVIEW.md).

Els scripts de `expanded-v1/provenance/` són una captura històrica del procés
d’anotació. Conserven els bytes i les rutes del checkout original; les eines
actuals es troben a `tools/` i s’obren amb `python3 -m benchmarks.calibration annotations`.
