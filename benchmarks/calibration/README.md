# Calibratge del detector i del tracking

**Comença aquí.** Aquest directori conté el banc experimental; els vídeos,
pesos, execucions i decisions humanes són fora del codi, a `data/` i `runs/`.

El detector de treball és **YOLOv8m a 0,001**, amb 0,002 com a control.
Ja s’han comparat 18 vídeos i hi ha una revisió humana de les anotacions en curs.
El següent estudi serà l’associació de deteccions amb **IDs estables**, tractant
les caixes parcials i solapades. Aquesta reorganització prepara el banc;
no incorpora encara un nou algorisme de tracking.

## On és cada cosa

| Directori | Què hi trobaràs |
| --- | --- |
| [config/](config/) | Corpus, matrius d’experiment i plans de les proves. |
| [annotations/](annotations/README.md) | Mostres i referències d’IA originals, amb la seva procedència. |
| [docs/](docs/STATE.md) | Estat de l’estudi, ús de la revisió, protocol de servidor i historial. |
| [engine/](engine/) | Executor, detector, mètriques i control de les iteracions. |
| [reviews/](reviews/) | Generació d’informes i pàgina de revisió humana. |
| [tools/](tools/) | Preparació de dades i extracció/dibuix de les anotacions. |
| [commands/](commands/) | Scripts de Docker usats per les comandes de prova. |
| [docker/](docker/) | Imatge i runtime del servidor NVIDIA. |
| [tests/](tests/) | Comprovacions del banc. |

## Les comandes habituals

Des de l’arrel del repositori, la porta d’entrada és sempre:

```bash
python3 -m benchmarks.calibration --help
```

**Continuar revisant anotacions i YOLO** — el servidor actual és
[localhost:8766](http://localhost:8766/). Per tornar-lo a iniciar si cal:

```bash
python3 -m benchmarks.calibration review serve
```

Si uses VS Code per SSH, reenvia el port 8766. Cada canvi es desa a
`runs/calibration/expanded-localization-v1/human-review/review-state.json`.
[Funcionament de la pàgina, correccions i còpies de seguretat](docs/HUMAN_REVIEW.md).

**Recalcular amb les decisions humanes**, escollint una carpeta de resultat nova:

```bash
python3 -m benchmarks.calibration review assess \
  --output runs/calibration/expanded-localization-v1/human-assessment-v1
```

**Comprovar la prova de 18 vídeos sense inferència**:

```bash
python3 -m benchmarks.calibration study expanded --dry-run
```

Les altres proves es conserven amb noms explícits:
`study thresholds`, `study low-thresholds` i `study localization`.
La construcció de Docker forma part d’aquestes comandes de servidor.
Cap prova s’inicia només per obrir el paquet o demanar l’ajuda.

## Quins resultats llegir

Els resultats complets són a `runs/calibration/expanded-localization-v1/`:

- `assessment/ASSESSMENT.md`: revisió de les dues confiances i resum per vídeo.
- `human-review/`: HTML, imatges i decisions de la revisió humana en curs.
- `human-assessment-r212/`: interpretació d’una primera revisió humana parcial.
- `inputs/`, `run/` i `review/`: inputs congelats, CSV, mètriques i galeria original.

La cobertura es calcula sobre fotogrames anotats; no acredita detecció en tots
els frames ni estabilitat d’identitat. Les anotacions sense revisar continuen
provisionals. [Estat actual i propera fase](docs/STATE.md).

Per als detalls menys habituals:
[servidor i transferència](docs/SERVER.md) · [historial de proves](docs/HISTORY.md) ·
[canvis de rutes i compatibilitat](docs/REORGANIZATION.md).
