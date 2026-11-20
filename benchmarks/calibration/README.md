# Banc de calibratge

**Comença per [l’estat actual](docs/STATE.md).** La fase de detecció i preparació
s’ha contrastat; el pas següent és estudiar la continuïtat d’ID del gimnasta.
Encara no hi ha una configuració de tracking òptima validada amb l’entrada actual.

## Què necessites obrir

| Necessitat | Punt d’entrada |
| --- | --- |
| Saber amb què treballem ara i què falta | [Estat actual](docs/STATE.md) |
| Revisar o corregir les anotacions | [Guia de revisió](docs/HUMAN_REVIEW.md) i [anotacions](annotations/README.md) |
| Executar una comanda | [Catàleg de comandes](commands/README.md) |
| Configurar el pipeline de producció | [Perfils del projecte](../../configs/pipelines/README.md) i [preparació](../../src/trampoline_vision/preparation/README.md) |
| Entendre decisions, experiments anteriors i imatges | [Estudis tancats](archive/README.md) |
| Afegir eines o preparar un estudi nou | [Estructura i convencions](docs/REORGANIZATION.md), [configuració](config/README.md) i [normes del repositori](../../AGENTS.md) |

## Mapa del directori

```text
calibration/
├── docs/          Estat i guies d’ús actuals.
├── annotations/   Referències i procedència; decisions humanes locals a runs/.
├── config/        Corpus compartit i plans nous en curs.
├── commands/      Comandes del servidor, amb catàleg d’actives i històriques.
├── engine/        Infraestructura compartida d’execució i avaluació.
├── tools/         Adaptadors i utilitats del banc.
├── reviews/       Revisió humana i generació d’informes.
├── tests/         Comprovacions del banc.
├── docker/        Entorn reproduïble.
└── archive/       Estudis tancats: informes, plans i evidències seleccionades.
```

Els JSON, CSV, `.gz` i imatges d’experiments tancats són dins d’`archive/`.
Les referències que encara usem continuen a `annotations/`; els resultats
complets, MP4, pesos i caches són locals a `runs/` i `data/`, fora de Git.
El codi de producció viu a `src/trampoline_vision/`.

```bash
python3 -m benchmarks.calibration --help
python3 -m benchmarks.calibration review serve
```

La revisió humana escolta a `http://localhost:8766/`; si treballes per SSH,
reenvia el port. Els estudis antics continuen disponibles al catàleg, però
cap prova s’executa només per consultar el banc.
