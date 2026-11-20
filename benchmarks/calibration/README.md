# Banc de calibratge

El detector de treball és **YOLOv8m a 0,001**, amb 0,002 com a control.
La preparació de fins a 12 caixes és un perfil explícit del projecte.
El criteri és que almenys una candidata localitzi el gimnasta,
encara que sigui parcial. El seguiment d’un ID estable s’avalua per separat.

| Si vols… | Obre… |
| --- | --- |
| Entendre què s’ha provat i evitar repetir experiments | [Estudi consolidat](docs/BOX_PREPARATION_STUDIES.md) i [evidències d’exemple](evidence/box-preparation-v1/index.json) |
| Saber què s’activa per defecte i com provar el perfil nou | [Configuracions de pipeline](../../configs/pipelines/README.md) i [API de preparació](../../src/trampoline_vision/preparation/README.md) |
| Llegir l’estat del detector i de l’avaluació temporal | [Estat de l’estudi](docs/STATE.md) |
| Revisar, corregir o exportar les anotacions | [Guia de revisió humana](docs/HUMAN_REVIEW.md) |
| Executar una bateria, comprovar recursos o reprendre-la | [Guia del servidor](docs/SERVER.md) |
| Consultar iteracions anteriors | [Historial](docs/HISTORY.md) |
| Localitzar els artefactes i decidir què es pot arxivar | [Estructura i conservació de resultats](docs/REORGANIZATION.md) |

Des de l’arrel del repositori:

```bash
python3 -m benchmarks.calibration --help
python3 -m benchmarks.calibration review serve
python3 -m benchmarks.calibration study representative-tracking --dry-run
```

La revisió humana escolta a localhost:8766. Si treballes per SSH,
reenvia el port. Els resultats locals més rellevants són:

- [Revisió humana de YOLO](../../runs/calibration/expanded-localization-v1/human-review/index.html).
- [Informe de localització en 18 clips](../../runs/calibration/expanded-localization-v1/assessment/ASSESSMENT.md).
- [Informe de la prova contínua en 12 clips](../../runs/calibration/representative-tracking-v1/ASSESSMENT.md)
  i [galeria de discrepàncies](../../runs/calibration/representative-tracking-v1/review.html).

Els fitxers anteriors viuen a runs i són artefactes locals. El codi, les
referències i la selecció d’evidències s’organitzen així:

| Directori | Contingut |
| --- | --- |
| [config](config/) | Corpus, matrius d’experiment i plans. |
| [annotations](annotations/README.md) | Referències provisionals i procedència. |
| [evidence](evidence/box-preparation-v1/index.json) | Resums, discrepàncies i imatges amb SHA-256. |
| [engine](engine/) i [tools](tools/) | Executor i adaptadors del banc. |
| [reviews](reviews/) | Informes i pàgina de revisió humana. |
| [commands](commands/) i [docker](docker/) | Comandes i entorn del servidor. |
| [tests](tests/) | Comprovacions del banc. |
