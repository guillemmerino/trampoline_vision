# Trampoline Vision

Sistema modular d'anàlisi de gimnàstica de trampolí a partir de vídeo 2D amb càmera fixa.
L'objectiu final és obtenir un diagnòstic esportiu; la primera etapa construeix el seguiment
del gimnasta i la detecció dels salts en escenes amb múltiples persones.

## Estat actual: seguiment executable de deteccions enregistrades

- Docker CPU amb FFmpeg/ffprobe, paquet instal·lat i servei Compose per executar proves.
- Contractes interns per a vídeo, fotogrames, punts BODY_25, deteccions i procedència.
- Lector de manifest i OpenPose JSON en ZIP o carpeta, sense extreure el ZIP.
- Temps reals de presentació del vídeo, índex intern zero-based i fotogrames buits explícits.
- Comanda `inspect` amb informe JSON i exportació opcional de deteccions en JSONL.
- Proves unitàries i d'integració, inclosa una amb vídeo sintètic i FFmpeg.
- Contractes de tracking amb procedència, candidats parcials i observació/predicció separades.
- Backends configurables: OC-SORT i ByteTrack (`trackers==2.6.1`), BoT-SORT (`boxmot==16.0.9`) amb/sense ReID OSNet.
- Entrada CSV de caixes independents, descriptors externs i cache incremental verificat.
- Preparació de candidats amb caixa de pose, score explícit i deduplicació opcional, amb proves sintètiques.

La comanda `visualize` genera vídeo anotat i informe per revisar coordenades i sincronització,
amb vistes all/filtered/compare i intervals temporals. Els llindars només afecten el dibuix.
La comanda `track` integra caixes independents o el baseline OpenPose, un tracker configurable i
identitats persistents, informe, JSONL i vídeo opcional. `evaluate-tracking`
compara l'exportació amb anotacions manuals disperses. La precisió sobre el
vídeo real continua pendent de validació. ReID pot executar inferència d’aparença;
la inferència de persones/poses, el matching d’esquelets, la coherència de l’actor,
la selecció del gimnasta, els salts, la puntuació i l’API continuen pendents.
La [guia de tracking](docs/19-tracking-contracts-and-backend.md) explica els contractes,
la biblioteca, els contractes i les seves limitacions.
La [guia de preparació](docs/20-pose-candidate-preparation.md) descriu el nou pas
i la configuració independent dels filtres visuals.

## Tracking de caixes i ReID (0.5.0)

El tracker de caixes manté les identitats; les poses independents s’hi associaran
en una fase posterior. Canvia `tracker_config` a
`configs/pipelines/track-boxes.json` per escollir `ocsort.json`, `bytetrack.json`,
`botsort.json` o `botsort-reid.json` de `configs/trackers/`.
La [guia de perfils i ReID](docs/27-configurable-box-tracking.md) explica
els fluxos, els pesos locals, el cache i els límits de cada adaptador.

```powershell
docker compose --profile reid build tracking-reid tests-tracking-reid
docker compose --profile reid run --rm tests-tracking-reid
docker compose --profile reid run --rm tracking-reid track --config configs/pipelines/track-boxes.json --start 0 --end 3 --output runs/boxes-01.json --video-output runs/boxes-01.mp4
```

El perfil amb ReID requereix els pesos verificats a `runs/reid-models/`;
ja existeixen en aquest equip des de l’estudi 05. La imatge és CPU i no
incorpora dades ni pesos. La regressió compara els tres clips amb l’estudi
anterior; el [protocol d’integració](benchmarks/studies/06-configurable-tracking/README.md)
distingeix aquesta comprovació d’una avaluació de precisió.

## Recovery: estructura preparada

`src/trampoline_vision/recovery/` reserva el mòdul posterior al tracking complet
per relacionar fragments amb actors. Els fitxers documenten responsabilitats;
encara no hi ha algoritme ni integració executable. Els perfils de recovery
són exemples de disseny desactivats. Vegeu el [pla de construcció](docs/28-recovery-package-design.md).

## Provar i validar el baseline OpenPose

```powershell
docker compose --profile tracking build tracking tests-tracking
docker compose --profile tracking run --rm tests-tracking
docker compose --profile tracking run --rm tracking track --config configs/pipelines/track-openpose.json --start 0 --end 3 --output runs/tracking-01.json --video-output runs/tracking-01.mp4
```

El baseline real i la correcció de confirmació 0.4.0 s'han estudiat als
trams 0–3 s i 14–17 s. La [comparació](docs/23-confirmation-fix-and-improvement-study.md)
explica què s'ha corregit i per què la identitat física encara no està validada.
La [guia de validació](docs/21-tracking-validation-guide.md) explica estats,
anotacions manuals, comparació de configuracions i criteris per millorar.

## Primera execució amb Docker

Des de la carpeta del projecte, amb Docker Desktop en mode Linux i en marxa:

```powershell
New-Item -ItemType Directory -Force runs | Out-Null
docker compose build replay
docker compose run --rm replay inspect --config configs/pipelines/inspect-openpose.json --output runs/reference-summary.json
```

`../TFM` es munta només per a lectura. Les dades existents no es copien a la imatge ni es modifiquen.
Si són en una altra ubicació, es pot definir `TFM_DATA_DIR` i ajustar el manifest corresponent.
Una sortida existent no se sobreescriu: utilitzar un nom nou per repetir l'execució.

Per exportar també totes les observacions internes, afegir:

```text
--frames-output runs/reference-frames.jsonl
```

Aquest fitxer pot ser gran. No és un vídeo ni conté identitats temporals.

## Vídeo anotat

```powershell
docker compose run --rm replay visualize --config configs/pipelines/visualize-openpose.json --start 0 --end 3 --view compare --output runs/review-short.mp4
docker compose run --rm replay visualize --config configs/pipelines/visualize-openpose.json --output runs/review-full.mp4
```

La capçalera s’afegeix fora de la imatge; els colors i IDs corresponen a deteccions, encara sense
tracking. La sortida és sense àudio i es comproven fotogrames i temps després de codificar.
Instruccions a la [guia de visualització](docs/17-visualization-guide.md).
La [revisió del cas actual](docs/18-reference-visual-review.md) recull artefactes, temps i limitacions observades.

## Proves en l'entorn CPU

```powershell
docker compose --profile test build tests
docker compose --profile test run --rm tests
```

## Execució local opcional

Python >= 3.10, FFmpeg instal·lat i `ffprobe` al PATH. Per visualitzar, instal·lar també l’extra `visualization` amb `pip install -e ".[visualization]"`. El paquet no requereix dependències Python
d'execució. La construcció necessita setuptools >= 61, que pip pot obtenir de l'índex configurat.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m trampoline_vision inspect --config configs/pipelines/inspect-openpose.json --output runs/local-summary.json
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

La prova amb vídeo sintètic s'omet explícitament si no hi ha FFmpeg/ffprobe; dins de Docker
s'executa. No cal GPU ni OpenPose instal·lat per reproduir les deteccions enregistrades.

## Configuració executable i disseny futur

`configs/pipelines/inspect-openpose.json`, `visualize-openpose.json`, `track-openpose.json`
i el manifest són executables (1.0). `track-boxes.json` i els perfils de tracker
són executables (2.0); el model d’aparença és una configuració 1.0 independent.
Els altres exemples de pipeline/model/escenari amb `design-only` documenten etapes futures i
no són acceptats com a configuració de la comanda actual.

El manifest relaciona explícitament vídeo i JSON. El cas inicial declara 930 fotogrames i índex
extern començant a 1. La durada de metadades de referència és 25 s, però el vídeo és de 31 s:
l'informe registra la discrepància. Les notes esportives no s'utilitzen en aquest recorregut.

## Documentació

- [Índex](docs/README.md), [intenció](docs/01-project-intent.md) i [arquitectura](docs/03-architecture-and-domains.md).
- [Contractes](docs/04-data-contracts.md) i [dades existents](docs/05-inputs-and-legacy-data.md).
- [Execució CPU i CLI](docs/15-cpu-replay-guide.md).
- [Guia de lectura del codi comentat](docs/16-code-reading-guide.md).
- [Validació](docs/12-validation-strategy.md) i [full de ruta](docs/13-development-roadmap.md).

El projecte és germà de TFM i no importa els seus scripts. Dades, pesos i resultats locals queden
fora del control de versions. La llicència de distribució del projecte encara s'ha de decidir.
