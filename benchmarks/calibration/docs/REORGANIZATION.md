# Estructura i canvi de rutes

El directori arrel passa de molts scripts, JSON i documents barrejats a un
README d’entrada i carpetes per funció. La comanda estable és
`python3 -m benchmarks.calibration`; els fitxers interns es poden reordenar
sense obligar a memoritzar-los.

| Abans, sota `benchmarks/calibration/` | Ara |
| --- | --- |
| `corpus.json`, `corpus-validation.json` | `config/` |
| `experiment.json`, `tracker-sensitivity.json` | `config/experiments/` |
| `iterations/*-experiment.json` | `config/experiments/` |
| `iterations/0*.json` | `config/iterations/` |
| `annotation-pilot/`, `annotation-expanded-v1/` | `annotations/pilot-v1/`, `annotations/expanded-v1/` |
| `run*.sh` | `commands/`; comanda recomanada `study …` |
| `run.py`, `iterate.py`, detector i avaluació | `engine/` |
| Informes, decisions i revisió humana | `reviews/` |
| HTML, CSS i JS de revisió | `reviews/static/` |
| Scripts d’extracció, preparació i dibuix | `tools/` |
| `Dockerfile` | `docker/Dockerfile` |
| `ITERATIONS.md`, `HUMAN_REVIEW.md`, protocol llarg | `docs/` |
| Validació inicial | `docs/history/initial-validation.json` |

Exemples de comandes actualitzades:

```bash
# Abans: python3 benchmarks/calibration/human_review.py serve
python3 -m benchmarks.calibration review serve

# Abans: bash benchmarks/calibration/run-expanded-localization.sh --dry-run
python3 -m benchmarks.calibration study expanded --dry-run

# Executor d’iteració per a opcions avançades:
python3 -m benchmarks.calibration iterate --help

# Eines d’anotació:
python3 -m benchmarks.calibration annotations extract --help
```

Els imports Python històrics, com `benchmarks.calibration.evaluation` o
`benchmarks.calibration.human_review`, continuen apuntant als mateixos mòduls
actuals. Això conserva els scripts de valoració offline guardats amb els runs.
Les antigues rutes físiques dels scripts es consulten a la taula anterior.
L’únic enllaç físic de compatibilitat, `common.py → engine/common.py`, permet
que els informes antics continuïn localitzant l’arrel del repositori. No duplica
la implementació.

Els paràmetres numèrics no canvien. Només s’ajusten els paths dels plans i perfils.
El corpus i els JSON de referències, selecció, decisions i procedència conserven
els seus bytes. La documentació s’actualitza per reflectir les comandes noves.

`data/calibration-v1/` i tots els resultats de `runs/calibration/` continuen al seu
lloc, incloent el paquet HTML en ús, les decisions humanes i l’historial.
Els informes congelats mantenen els noms/rutes del codi que els va produir;
no s’han reescrit per fer-los semblar execucions noves.

La còpia del codi anterior i el manifest de moviments són a
`runs/calibration/reorganization-v1/`. Permeten reconstruir el checkout anterior
per reproducció estricta. Reprendre una inferència comprova també els hashes del
codi: aquesta comprovació continua activa després de la reorganització.
