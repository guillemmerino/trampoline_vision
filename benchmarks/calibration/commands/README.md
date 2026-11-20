# Comandes del banc

Executa-les des de l’arrel del repositori. Consulta l’ajuda sense iniciar cap prova:

```bash
python3 -m benchmarks.calibration --help
```

## Eines de treball actuals

| Comanda | Responsabilitat |
| --- | --- |
| `bash benchmarks/calibration/commands/run-identity-comparison.sh` | Preflight del [protocol d’identitat](../config/studies/identity-continuity-v1.md); `--execute` inicia la bateria pendent. |
| `python3 -m benchmarks.calibration review serve` | Revisió humana amb persistència de decisions. |
| `python3 -m benchmarks.calibration review-boxes --help` | Galeria del codi de preparació actual, sense tracker. |
| `python3 -m benchmarks.calibration prepare-boxes --help` | Preparació conservadora de deteccions desades. |
| `python3 -m benchmarks.calibration annotations --help` | Extracció i eines de referències. |
| `python3 -m benchmarks.calibration verify --help` | Verificació del paquet portable. |

El tracking de producció s’executa amb `python3 -m trampoline_vision track` i
un [pipeline explícit](../../../configs/pipelines/README.md).

## Reproducció d’estudis tancats

| Entrada `study` | Script | Estudi |
| --- | --- | --- |
| `thresholds` | `run-iteration.sh` | Robustesa dels llindars del detector i quatre trackers. |
| `low-thresholds` | `run-low-thresholds.sh` | Llindars baixos. |
| `localization` | `run-localization.sh` | 0,001 principal i 0,002 control en tres clips. |
| `expanded` | `run-expanded-localization.sh` | Localització en 18 clips. |
| `representative-tracking` | `run-representative-tracking.sh` | Antecedent ByteTrack sobre 12 clips. |
| `zones` | `run-zone-comparison.sh` | Comparació aparellada de zones en 18 clips. |

Exemple de preflight sense executar la comparació:

```bash
python3 -m benchmarks.calibration study zones --dry-run --output /results/zone-comparison-check
```

La destinació ha de ser nova. Els paràmetres i les limitacions són a
[l’estudi arxivat](../archive/detection-preparation-v1/README.md).
`run-server.sh` és la base Docker/NVIDIA dels wrappers de detector/tracking;
la comparació de zones és CPU i no requereix models. Els noms dels scripts
es conserven perquè les comandes anteriors continuïn sent reconeixibles.
