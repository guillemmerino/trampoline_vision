# Detecció i preparació — estudi tancat v1

**Decisió de treball:** YOLOv8m a 0,001 i preparació representativa de màxim
12 candidates, amb zona comuna centrada `soft`. Les referències IA continuen
provisionals. Aquesta fase no acredita un ID estable durant tot el vídeo.

## Ordre de lectura

1. [Decisions de detecció](docs/DETECTION_DECISIONS.md): recorregut raonat,
   llindars estudiats, problemes i motius d’acceptació o rebuig.
2. [Variants de preparació](docs/BOX_PREPARATION_STUDIES.md): contenció,
   ancoratges, densitat, regions, silueta i pressupost de candidates.
3. [Comparació de zones](docs/ZONE_COMPARISON.md): antiga hard, antiga soft i
   central soft; conserva 56/56 caixes útils humanes i canvia 1078 → 1077/1267
   al diagnòstic de cobertura IA90. El cas nou continua localitzant el gimnasta.
4. [Historial del protocol](docs/HISTORY.md): com es van plantejar les iteracions.

## Què hi ha en cada carpeta

| Carpeta | Responsabilitat |
| --- | --- |
| `docs/` | Informes i interpretació de l’estudi. `history/` conté validació inicial històrica. |
| `config/iterations/` | Plans acotats de cada prova; `archive/` conté l’esborrany substituït. |
| `config/experiments/` | Matrius exactes de detector i tracker utilitzades pels plans. |
| `evidence/box-preparation-v1/` | Selecció petita de resums, taules i dotze imatges representatives. |

No són bolcats de totes les execucions. L’[índex d’evidències](evidence/box-preparation-v1/index.json)
identifica l’origen i els SHA-256. `*.json` conté dades estructurades;
`*.csv`, taules; `*.gz`, JSON/CSV comprimits amb més detall; `images/`, casos
visuals. Cal conservar aquesta evidència per contrastar les conclusions sense
repetir experiments. Els resultats complets continuen a `runs/calibration/`.

## Reproducció i frontera amb el codi actiu

Les [comandes històriques](../../commands/README.md) continuen disponibles.
Els executors són compartits a `engine/` i `tools/`; la selecció de producció
és a [src/preparation](../../../../src/trampoline_vision/preparation/README.md).
`engine/representative.py` es manté com a comparador històric congelat.
Les anotacions es mantenen a [annotations/](../../annotations/README.md)
perquè encara s’utilitzen en la revisió humana i les comparacions noves.

En aquesta reorganització s’han conservat els bytes de les evidències i
les anotacions. Només s’han corregit rutes dels plans executables i enllaços.
Els hashes antics de plans/codi identifiquen el checkout que va fer la prova:
per repetir-la amb aquestes rutes cal una sortida nova, no reprendre un run antic.
