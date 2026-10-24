# Trampoline Vision

Sistema modular d'anàlisi de gimnàstica de trampolí a partir de vídeo 2D amb càmera fixa.
L'objectiu final és obtenir un diagnòstic esportiu; la primera etapa construeix el seguiment
del gimnasta i la detecció dels salts en escenes amb múltiples persones.

## Estat actual: passos 1 i 2

- Docker CPU amb FFmpeg/ffprobe, paquet instal·lat i servei Compose per executar proves.
- Contractes interns per a vídeo, fotogrames, punts BODY_25, deteccions i procedència.
- Lector de manifest i OpenPose JSON en ZIP o carpeta, sense extreure el ZIP.
- Temps reals de presentació del vídeo, índex intern zero-based i fotogrames buits explícits.
- Comanda `inspect` amb informe JSON i exportació opcional de deteccions en JSONL.
- Proves unitàries i d'integració, inclosa una amb vídeo sintètic i FFmpeg.

Encara no s'executen inferència, deduplicació, tracking, selecció del gimnasta, detecció de salts,
puntuació, API ni vídeo anotat. La comprovació visual de sincronització és el pas 3.

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

## Proves en l'entorn CPU

```powershell
docker compose --profile test build tests
docker compose --profile test run --rm tests
```

## Execució local opcional

Python >= 3.10, FFmpeg instal·lat i `ffprobe` al PATH. El paquet no requereix dependències Python
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

`configs/pipelines/inspect-openpose.json` i el manifest de referència són executables (versió 1.0).
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
