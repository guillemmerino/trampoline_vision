# Estructura, arxiu i conservació

## Regla estable

El banc separa **treball actual**, **eines compartides**, **referències** i
**estudis tancats**. El [README d’entrada](../README.md) dona accés a cada grup.
Les [normes del repositori](../../../AGENTS.md) fixen la mateixa disciplina
per als canvis futurs: responsabilitats clares, docstrings i comentaris en
català, procedència i comprovació de rutes després de moure fitxers.

| Ubicació | Responsabilitat |
| --- | --- |
| `src/trampoline_vision/` | Implementació reutilitzable de producció. |
| `configs/` del projecte | Perfils executables de l’aplicació. |
| `calibration/docs/` | Estat i guies d’ús actuals. |
| `calibration/config/` | Corpus compartit i plans nous en curs a `studies/`. |
| `calibration/annotations/` | Referències reutilitzades i procedència. |
| `calibration/commands/`, `engine/`, `tools/`, `reviews/` | Eines compartides i executors, amb catàlegs de responsabilitats. |
| `calibration/archive/<estudi>/` | Plans, informes i selecció d’evidències d’estudis tancats. |
| `runs/`, `data/`, caches i pesos | Artefactes locals; es regeixen per `.gitignore`. |

## Moviments d’aquesta reorganització

| Ruta anterior sota calibration | Ruta actual |
| --- | --- |
| `evidence/` | `archive/detection-preparation-v1/evidence/` |
| `config/experiments/` | `archive/detection-preparation-v1/config/experiments/` |
| `config/iterations/` | `archive/detection-preparation-v1/config/iterations/` |
| `config/corpus-validation.json` | `archive/detection-preparation-v1/config/corpus-validation.json` |
| `docs/DETECTION_DECISIONS.md`, `BOX_PREPARATION_STUDIES.md`, `ZONE_COMPARISON.md`, `HISTORY.md` | `archive/detection-preparation-v1/docs/` |
| `docs/history/` | `archive/detection-preparation-v1/docs/history/` |
| Estat extens anterior a `docs/STATE.md` | `archive/detection-preparation-v1/docs/STATE_HISTORY.md`; STATE actual es manté breu. |

S’han actualitzat els enllaços, les constants de rutes, els defaults dels
executors i les referències relatives dels plans i perfils d’experiment.
Els paràmetres científics no canvien. Les evidències i les anotacions conserven
els seus bytes, incloent els JSON/CSV comprimits i les dotze imatges seleccionades.
No s’han mogut ni eliminat resultats de `runs/`, dades o decisions humanes.

Els scripts de servidor mantenen els noms. `python3 -m benchmarks.calibration`
continua sent l’entrada estable; consulta el [catàleg](../commands/README.md).
Els imports de compatibilitat i `common.py → engine/common.py` es mantenen
per als scripts de revisió offline. No es creen còpies alternatives del motor.

Canviar rutes de plans o codi canvia la seva identitat. Els runs congelats
continuen descrivint el checkout original; els seus hashes no es reescriuen.
Per reproduir un estudi amb les rutes noves, usa una destinació nova.
No reprenguis una execució antiga sobre un pla modificat.

## Quan es tanca una prova nova

1. Desa l’informe i una selecció petita d’evidències contrastables.
2. Agrupa pla, configuració i resultats seleccionats a `archive/<estudi>/`.
3. Afegeix un README amb decisió, limitacions i com reproduir-lo.
4. Actualitza estat, catàlegs i enllaços; verifica les rutes i els tests afectats.
5. Conserva les dades completes a `runs/` o en un arxiu extern verificat.

## Resultats locals i retenció

`expanded-localization-v1` continua actiu: revisió humana i deteccions reutilitzades.
`sample-expansion-preparation-v1/raw` permet reconstruir la galeria.
`representative-tracking-v1` conserva el replay i les discrepàncies temporals.
`zone-comparison-v1` conserva la comparació aparellada i la revisió visual.

Les simulacions antigues i `box-preparation-v1/v2` es poden arxivar fora de
l’espai de treball després de copiar-les i verificar-les. Aquesta reorganització
no les elimina. Els resums versionats són una selecció científica, no un
substitut de totes les traces si es vol reproducció estricta.

## Verificació de la reorganització

Passen els 76 tests del banc, incloent resolució dels plans i perfils,
compatibilitat d’imports, enllaços dels punts d’entrada i hashes d’evidències.
La comprovació de tots els enllaços Markdown del banc no ha trobat destinacions
absents. S’han contrastat els 34 fitxers d’evidència contra el commit anterior:
conserven exactament els bytes, igual que les dades i captures d’anotació.
El preflight CPU de zones continua resolent 18 vídeos i 1.440 mostres sense
crear resultats ni repetir inferència. Només s’han retirat caches Python
regenerables; no s’han eliminat dades de l’estudi.
