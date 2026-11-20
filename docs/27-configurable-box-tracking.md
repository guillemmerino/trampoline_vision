# Tracking de caixes configurable i ReID — versió 0.5.0

## Responsabilitat i flux

El tracker de caixes és el responsable de la identitat temporal. No necessita
OpenPose per seguir persones. L'aparença és una evidència addicional que pot
consumir BoT-SORT; no és un segon tracker ni el selector del gimnasta.

L’objectiu actual de calibratge prioritza que l’ID del gimnasta es mantingui
associat a la mateixa persona. La caixa pot créixer o canviar de forma si
ajuda a mantenir-la localitzada; el marge i la inclusió temporal d’un assistent
són costos acceptables, mentre que transferir-li l’ID és un error.
La precisió de les articulacions i la seva coherència es revisaran després
de reconstruir els esquelets i associar-los a aquestes identitats.
Aquesta és una prioritat d’estudi: no acredita que els backends actuals ja
la satisfacin ni canvia les mesures originals exportades.
[Criteris i estat de la fase](../benchmarks/calibration/docs/STATE.md).

```text
Vídeo original + caixes de persona enregistrades
    ingestion → FrameDetections[PersonBoxDetection]
    preparation → TrackingFrame[BoxMeasurement(source="detector")]
                     │
                     ├─ píxels originals → perception.appearance → FrameAppearance
                     │                       ↕ cache de descriptors
                     ↓
    tracking.factory → OC-SORT / ByteTrack / BoT-SORT
    TrackingSession → identitats, observacions, prediccions i transicions
    application.tracking → informe JSON + frames JSONL + MP4 opcional
```

En una fase posterior, poses independents produiran esquelets en les mateixes
coordenades i temps. Un component de matching associarà esquelets amb les
caixes/identitats. No haurà de crear la identitat temporal a partir de
l'ordre de les persones d'OpenPose. Aquest matching i el mòdul de coherència
de l'actor encara no s'executen.

Si la reconstrucció utilitza retalls de les caixes o reescalat, cal conservar
les transformacions per retornar les articulacions a coordenades del fotograma
original. Les trajectòries articulars no s’han de confondre amb el moviment
del centre ni dels límits variables de la caixa.

La lectura OpenPose existent continua disponible com a baseline històric
amb caixes derivades de pose. El nou recorregut de caixes no crea 25
articulacions absents per simular una pose i no aplica la deduplicació
geomètrica dissenyada per a hipòtesis de pose multirotació.

## Fitxers i fronteres

| Component | Responsabilitat |
| --- | --- |
| `contracts/geometry.py` | Caixa immutable compartida; `contracts.tracking.BoundingBox` manté l'import antic. |
| `contracts/observations.py` | `PersonBoxDetection`, geometria/confiança originals i procedència, sense esquelet. |
| `contracts/appearance.py` | Vectors normalitzats per `candidate_id`, context i fingerprint del model. |
| `ingestion/recorded_boxes.py` | CSV de persones; valida ordre, IDs locals, geometria, confiança i cobertura. |
| `ingestion/detections.py` | Selecció del lector segons el manifest. |
| `ingestion/tracking_config.py` | Resol pipeline → perfil → model; cada ruta és relativa al fitxer que la declara. |
| `perception/appearance/` | Configuració i extractor OSNet; no assigna identitats. |
| `preparation/boxes.py` | Preparació de caixes configurable, amb fonts intactes; la contenció no assigna identitat. |
| `results/preparation.py` | Auditoria completa de preparació, independent del JSONL compacte de tracking. |
| `infrastructure/embedding_cache.py` | Persistència SQLite de descriptors verificables, independent del tracker. |
| `tracking/backend.py` | Port d'associació; sense dependències visuals en importar-lo. |
| `tracking/factory.py`, `tracking/backends/` | Registre explícit i adaptadors de biblioteques fixades. |
| `tracking/session.py` | Seqüència, confirmació comuna, IDs de domini i transicions. |
| `application/appearance.py` | Coordina descodificació original, extracció i cache. |
| `application/tracking.py`, `results/` | Cas d'ús i artefactes per als mateixos contractes, sigui quin sigui el backend. |

## Escollir el tracker

El pipeline executable és `configs/pipelines/track-boxes.json`, esquema **2.0**.
Per canviar de tracker només cal canviar el valor de `tracker_config`:

```json
{
  "schema_version": "2.0",
  "task": "track_recorded_detections",
  "case_manifest": "../../data/manifests/JPN_AGE_1_000905_31.0.boxes.example.json",
  "tracker_config": "../trackers/botsort-reid.json",
  "missing_frames_policy": "error"
}
```

| Perfil a `configs/trackers/` | Implementació | Aparença |
| --- | --- | --- |
| `ocsort.json` | OC-SORT, `trackers==2.6.1` | No |
| `bytetrack.json` | ByteTrack, `trackers==2.6.1` | No |
| `botsort.json` | BoT-SORT, `boxmot==16.0.9` | No |
| `botsort-reid.json` | El mateix BoT-SORT | OSNet x0.25 MSMT17 preentrenat |

Els paràmetres s'agrupen en `lifecycle` (política comuna), `parameters`
(opcions del tracker concret) i `appearance` (referència al model o `null`).
Les claus desconegudes, paràmetres d'un altre backend, duplicació de perfil
i configuració inline, o ReID en un tracker que no el consumeix són errors.
Llegir configuració no importa Torch ni carrega pesos.

Els pipelines inline **1.0** d'OC-SORT i els arguments Python antics continuen
acceptats. La configuració efectiva dels informes 0.5 agrupa els paràmetres
per backend; els consumidors han de consultar també `software_version`.
Els prefixos públics són `ocsort:`, `bytetrack:` i `botsort:`; una identitat
només és interpretable dins de la seva execució (`run_id`).

## Evidència i vida d'una identitat

Els perfils inicials mantenen confiança forta **0,10**, confirmació amb
**3 associacions fortes consecutives** i retenció nominal **0,5 s**. ByteTrack
i BoT-SORT admeten evidència feble a partir de **0,02**. Són valors inicials
del protocol anterior, pendents de calibrar.

Una mesura feble pot mantenir una identitat ja confirmada; no confirma un
naixement. Una pèrdua o una associació feble interromp la ratxa inicial.
El tracker pot reservar hipòtesis internes abans que el domini publiqui un
ID. La recuperació d'una identitat confirmada no exigeix una nova ratxa.
Les caixes observades exportades són les mesures originals; les prediccions
no contenen articulacions ni es compten com a observacions.

OC-SORT i ByteTrack reben els timestamps reals per l'API de `trackers`.
L'adaptador BoT-SORT actual usa el comptador de frames de BoxMOT: el cas d'ús
rebutja vídeo VFR. La compensació de càmera és explícitament identitat,
adequada al supòsit actual de càmera fixa. BoxMOT pot conservar una identitat
un tick addicional a la llista pública de perduts durant la retirada; no
es declara un límit estricte de 0,5 s per aquest backend.

El port aïlla els mètodes públics d'assignació d'IDs globals de BoxMOT amb
un bloqueig compartit i comptadors locals. Les sessions construïdes per
aquest adaptador poden intercalar-se sense reiniciar els IDs d'una altra.
Les instàncies BoxMOT s'han de crear a través del port, no directament en
altres fils que evitin aquest bloqueig.

## Manifest del CSV

El nou manifest conserva l'esquema 1.0, amb `format: "person_boxes_csv"`.
Exigeix coordenades de píxel originals, base d'índex explícita i
`frame_coverage` explícita. No declara `skeleton_schema`.

```csv
frame,det_id,x1,y1,x2,y2,conf,class_id
0,0,204,419,294,630,0.6213798522949219,0
```

La capçalera conté exactament aquests camps, amb ordre de columnes lliure.
`frame` és no decreixent; les caixes han de ser finites, positives i dins
del vídeo original. `conf` és entre 0 i 1 i `class_id` és 0 (persona).
`det_id` és un enter local al fotograma, mai una identitat temporal.
El lector ordena aquests IDs localment i conserva la fila CSV de procedència.

`complete_video` declara que la manca de files significa cap detecció;
`listed_frames_only` significa que el registre falta. Un CSV no pot demostrar
per si mateix que un detector hagi processat els frames sense deteccions:
aquesta declaració l'ha de proporcionar qui genera o coneix la font.
L'última opció informa `missing` o falla amb la política `error`.

## OSNet i cache

`configs/models/osnet-msmt17.json` declara pesos locals, SHA-256, dispositiu,
nombre de fils i carpeta de cache. El model admès és `osnet_x0_25_msmt17.pt`,
amb SHA-256 `6f57607fed9f502b9efed546108132ee715df5a5b6e6932c6269bacb47f59f99`.
Els pesos de l'estudi 05 ja són a `runs/reid-models/` en aquest equip;
no formen part de Git ni de la imatge Docker. L'origen i la preparació
verificada es documenten al [protocol 05](../benchmarks/studies/05-reid/protocol.json)
i el seu `prepare_weights.py`.

L'extractor comprova els bytes i els 565 tensors del backbone, carrega amb
`weights_only=True`, fa retalls sobre el vídeo original, preprocessament
RGB ImageNet a 256×128 i descriptors de 512 components normalitzats.
La xarxa es carrega al primer miss amb candidats; no hi ha descàrregues
implícites ni un segon model dins del tracker. No s'entrena cap model.
`device: "cpu"` és el perfil validat; CUDA exigeix entorn/PyTorch compatibles
i dispositiu disponible, amb una identitat de cache diferent.

El cache incremental SQLite identifica vídeo i CSV per contingut, timeline,
pesos, preprocessament, versions, dispositiu i fils. Cada frame també valida
IDs, ordre i geometria/confiança dels candidats, dimensió i checksum dels
vectors. Canviar llindars del tracker reutilitza aparença; canviar el vídeo,
les caixes o el model crea una identitat nova. Una corrupció es comunica,
no se substitueix silenciosament. Les escriptures són atòmiques per frame
i un procés interromput conserva els frames complets vàlids.

Amb MP4, ReID consumeix els mateixos píxels descodificats que el renderitzat.
Sense MP4 i amb cache complet no cal descodificar ni carregar la xarxa.
L'informe distingeix `model_loaded`, `extracted_candidates`, hits i misses.

## Executar i validar

Des de l'arrel del projecte, amb `runs/` existent:

```powershell
docker compose --profile reid build tracking-reid tests-tracking-reid
docker compose --profile reid run --rm tests-tracking-reid
docker compose --profile reid run --rm tracking-reid track --config configs/pipelines/track-boxes.json --start 0 --end 3 --output runs/boxes-01.json --video-output runs/boxes-01.mp4
```

Els quatre perfils es poden executar al runtime complet. OC-SORT i ByteTrack
també funcionen al servei lleuger `tracking`. Les sortides existents no se
sobreescriuen; cal un nom nou en cada prova. L'entrada TFM és de només lectura.
La imatge actual de ReID és CPU; el desplegament CUDA es prepararà al servidor.

La regressió reproduïble és a
`benchmarks/studies/06-configurable-tracking/verify_integration.py`.
Compara les nou traces dels tres clips de l'estudi 05, comprovant
assignacions, estats, prediccions i esdeveniments exactes, després de traduir
únicament els prefixos d'IDs. També executa ByteTrack sobre els tres clips,
contrasta descriptors reals en tres instants per clip i verifica inferència,
vídeo i replay amb cache des del cas d'ús públic. Vegeu el README de l'estudi
per a la comanda i el resum dels resultats.

Aquesta verificació prova integració i absència de regressions. No converteix
el resultat del pilot en seguiment fiable del gimnasta. La fragmentació i
les transferències d'actor descrites al document 26 continuen sent el punt
de partida per estudiar el mòdul de coherència/recuperació i el futur matching
de poses, abans de validar segmentació de salts o puntuacions.
