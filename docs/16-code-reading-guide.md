# 16. Guia de lectura del codi

El codi executable i les proves tenen docstrings en català a cada mòdul, classe, funció i mètode.
Els comentaris dels camps expliquen unitats, àmbits dels identificadors i absències. Els comentaris
de blocs expliquen decisions del flux, sense substituir les validacions que executa el programa.

## Ordre recomanat

1. [observations.py](../src/trampoline_vision/contracts/observations.py): què circula pel sistema.
2. [manifest.py](../src/trampoline_vision/ingestion/manifest.py): quines fonts formen un cas.
3. [video.py](../src/trampoline_vision/ingestion/video.py): d'on surten temps i dimensions.
4. [openpose.py](../src/trampoline_vision/ingestion/openpose.py): conversió dels JSON a observacions.
5. [inspection.py](../src/trampoline_vision/application/inspection.py): consum i resum de les dades.
6. [main.py](../src/trampoline_vision/interfaces/cli/main.py): com s'activa el recorregut des de terminal.
7. [visualization.py](../src/trampoline_vision/application/visualization.py), [overlay.py](../src/trampoline_vision/results/overlay.py) i [video.py de resultats](../src/trampoline_vision/results/video.py): dibuix i codificació del pas 3.
8. [proves](../tests/): quins errors i comportaments es comproven.

## Com llegir un contracte

La docstring de la classe explica el concepte i el seu consumidor. Els camps anotats declaren
la forma esperada i els comentaris n'expliquen el significat. `__post_init__` conté les comprovacions
que s'executen després del constructor de dataclass. L'anotació de tipus, tota sola, no valida
els valors a runtime. `frozen=True` impedeix reassignar camps; no és un sistema general de còpia
profunda ni de validació de qualsevol objecte mutable que s'hi pugui passar.

Les propietats `frame_count` i `duration_s` de `VideoAsset` es calculen a partir de la línia temporal,
evitant guardar valors duplicats que podrien divergir. `frame(index)` crea context, no llegeix píxels.
Els punts d'una detecció tenen ordre semàntic BODY_25 fix; un punt absent conserva la seva posició.

`DetectionProvenance` documenta d'on surt una dada. `detection_id` identifica una proposta en un
fotograma; el tracking futur definirà una identitat temporal diferent. `valid` indica la política
d'observació de l'entrada i `in_frame` els límits geomètrics; cap dels dos garanteix que el punt
anatòmic estigui ben estimat.

## Fronteres dels mòduls

| Fitxer | Entrada → sortida | Per què està separat |
| --- | --- | --- |
| `ingestion/json_io.py` | Text/fitxer → diccionari JSON | Tractament compartit de codificació, claus duplicades i errors de sintaxi. |
| `ingestion/errors.py` | Tipus d'error | La CLI pot distingir errors esperats de configuració, vídeo i deteccions. |
| `ingestion/manifest.py` | JSON → `CaseManifest` | Resol fonts i declaracions abans de llegir-les. |
| `ingestion/video.py` | Vídeo → `VideoAsset` | Separa l'execució de ffprobe de la conversió temporal, que es pot provar amb JSON sintètic. |
| `ingestion/openpose.py` | JSON/ZIP + context → `FrameDetections` | El format d'OpenPose queda a la frontera, sense entrar als futurs trackers. |
| `application/inspection.py` | Observacions → informe i stream opcional | El cas d'ús es pot cridar des d'una altra interfície sense arguments de terminal. |
| `interfaces/cli/main.py` | Arguments → codi de sortida i artefactes | L'elecció de rutes i la publicació són responsabilitats de la interfície actual. |
| `__main__.py` | `python -m` → CLI | Reutilitza la mateixa funció que la comanda instal·lada. |

`iter_openpose_frames` és un generador: el seu cos llegeix quan es demana el següent element.
El vídeo governa la iteració; el ZIP aporta registres quan existeixen. Això preserva també el
fotograma sense JSON. Un JSON vàlid amb `people: []`, un JSON absent i un JSON malformat tenen
resultats diferents. Les docstrings expliquen com afecta això la política `report` o `error`.

Els `__init__.py` expliquen el paper de cada domini. Els de tracking, selecció, segmentació,
puntuació, API i worker indiquen explícitament que encara són espais reservats. Importar-los
no inicia cap procés ni implementa les capacitats futures descrites.

## Fitxers d'execució

El [Dockerfile](../Dockerfile) explica les etapes builder, CPU i test. [compose.yaml](../compose.yaml)
explica els serveis puntuals, els muntatges i les rutes. [pyproject.toml](../pyproject.toml) explica
les metadades, el layout `src/`, la versió i el punt d'entrada CLI. `.dockerignore`, `.gitignore`
i `.editorconfig` documenten què queda fora de les imatges o del repositori i les convencions d'edició.

Els comentaris no canvien els valors, opcions o ordres. Els missatges d'error i l'ajuda de la CLI
es conserven tal com estaven per mantenir el comportament d'aquest increment de documentació.

## JSON de configuració

JSON estàndard no admet comentaris. Aquests fitxers es mantenen llegibles pels carregadors;
la seva explicació és aquí i als documents [05](05-inputs-and-legacy-data.md) i
[10](10-configuration.md).

| Fitxer | Claus i intenció |
| --- | --- |
| [visualize-openpose.json](../configs/pipelines/visualize-openpose.json) | Configuració executable del pas 3: fonts i política de buits compartides, més l’estil `render`. Els llindars no alteren les dades. |
| [inspect-openpose.json](../configs/pipelines/inspect-openpose.json) | `schema_version` i `task` identifiquen el contracte executable; `case_manifest` resol les fonts; `missing_frames_policy` determina si s'informen o es rebutgen registres absents. |
| [Manifest del cas](../data/manifests/JPN_AGE_1_000905_31.0.example.json) | `video` i `detections.primary` relacionen fonts; `frame_index_base`, `skeleton_schema` i `coordinate_space` eviten inferències ambigües; `expected` i `reference_metadata` donen context de comparació; `known_issues` informa limitacions. `detections.comparison` descriu un CSV futur que el recorregut actual no consumeix. |
| [replay-openpose.example.json](../configs/pipelines/replay-openpose.example.json) | Documenta el pipeline complet futur. `design-only` i les estratègies `unselected` indiquen que no es pot executar com a inspecció actual. |
| [openpose-recorded.example.json](../configs/models/openpose-recorded.example.json) | Descriu una font enregistrada i el seu esquema. `executes_inference: false` deixa clar que no activa OpenPose. És una proposta futura, no una configuració carregada per la CLI actual. |
| [fixed-camera-trampoline.example.json](../configs/scenarios/fixed-camera-trampoline.example.json) | Documenta càmera fixa, múltiples actors, un objectiu i regions encara no definides. La política de selecció continua pendent de prova. |

## Com llegir les proves

Per al recorregut complet de seguiment, la [guia 21](21-tracking-validation-guide.md)
ordena els fitxers de configuració, backend, sessió temporal, cas d'ús, exportació,
dibuix i avaluació. Les proves sintètiques inclouen l'API real de la biblioteca,
seqüències amb pèrdua/recuperació/expiració, vídeo VFR i fallades de publicació.

Per al preparador, llegir `preparation/config.py`, `pose.py`, `deduplication.py`
i `pipeline.py`, en aquest ordre. Les proves `unit/test_preparation.py` i
`integration/test_preparation.py` cobreixen geometria, agrupació i la connexió
amb el lector. La [guia 20](20-pose-candidate-preparation.md) explica cada política.

Per al nou límit de seguiment, llegir `contracts/tracking.py` i la
[guia 19](19-tracking-contracts-and-backend.md). `tests/unit/test_tracking_contracts.py`
prova geometria, procedència, candidats parcials i assignacions;
`tests/integration/test_ocsort_dependency.py` comprova l'API externa amb caixes
sintètiques si s'ha instal·lat l'extra. L'adaptador complet es prova també a
`tests/integration/test_tracking.py`.

[helpers.py](../tests/helpers.py) construeix fixtures temporals. El seu vídeo placeholder només
serveix quan s'injecten metadades; no és un MP4 descodificable. La prova amb FFmpeg genera un vídeo real.
`setUp` prepara l'aïllament de cada prova i `addCleanup` en programa la neteja. La docstring de
cada test explica el comportament protegit, especialment les regressions d'índexs, buits i últim fotograma.

## Verificació dels comentaris

Per comprovar que aquest increment és documental, es comparen els arbres sintàctics Python
abans i després d'eliminar-ne les docstrings. També es comprova la cobertura documental de tots
els mòduls, classes i funcions. Les configuracions i els JSON conserven els seus valors.
