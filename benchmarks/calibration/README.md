# Calibratge de detector i tracking al servidor

Aquest banc prepara dades portables i executa experiments amb els casos d'ús
actuals de tracking. És experimental. No modifica els perfils habituals, no
executa OpenPose, no activa recovery i no declara una configuració guanyadora
sense referències revisades. No necessita l'API.

## Corpus trobat i selecció

`corpus.json` fixa els bytes de **94 vídeos originals** de
`TFM/jumping_score/output_clips`, amb 82.890 fotogrames i 46 min 03 s.
Tots tenen 960 × 1080 i 30 FPS segons l'inventari inicial.

| Grup de font | Clips | Mida de vídeos |
| --- | ---: | ---: |
| JPN AGE 1 | 43 | 126,1 MiB |
| JPN AGE 2 | 41 | 94,9 MiB |
| JPN AGE 3 | 10 | 24,7 MiB |

El corpus és exploratori: mateix context de competició/captura, possibles
solapaments temporals i esportistes compartits. AGE no es presenta com una
separació train/test. Els tres clips dels estudis anteriors són coneguts;
cap vídeo es proclama holdout independent. No s'han utilitzat les notes S1–S10.

S'ha revisat una làmina amb el fotograma central dels 94 clips. Hi apareixen
inversions, assistents, jutges, canvis de costat del gimnasta i panells de
retransmissió/franges negres. Aquesta mostra no certifica tota la identitat
ni tota la captura de cada vídeo. Es conserven els píxels originals, sense ROI.

| Suite | Vídeos | Ús |
| --- | ---: | --- |
| `smoke` | 3 | Casos històrics per comprovar la instal·lació. Cal filtrar variants per fer-la curta. |
| `pilot` | 18 | Sis per AGE, incloent casos històrics, dispersió temporal i clips curts/llargs. 9 min 36 s. |
| `all` | 94 | Ampliació del mateix estudi; no és una prova independent de generalització. |

El paquet inclou també **YOLOv8n, YOLOv8m i OSNet** locals, amb SHA-256.
No depèn del directori TFM al servidor. Els vídeos i pesos no entren a Git.

## Preparar i traslladar

En aquest equip ja s'han creat `data/calibration-v1/`,
`runs/calibration-transfer-v1.tar` i `runs/calibration-transfer-v1.tar.sha256`.
L'arxiu té 319.723.520 bytes, aproximadament 305 MiB, incloent els models.
Els originals de TFM s'han llegit, sense modificar-los.

Per regenerar la còpia en una destinació nova o completar-ne una d'interrompuda:

```powershell
python -B benchmarks/calibration/prepare.py --tfm-root ../TFM --destination data/calibration-v1 --archive runs/calibration-transfer-v1.tar
```

Si l'arxiu ja existeix, ometre `--archive` o escollir-ne un de nou. La preparació
rebutja inputs canviats i còpies existents amb hashes incorrectes; no els sobreescriu.

**El codi nou i els manifests s'han de cometre i publicar al repositori abans
que un `git pull` els pugui obtenir.** El pull no transfereix el paquet de dades.
Traslladar el `.tar` i el `.sha256` per SCP/rsync o el mecanisme habitual.
No cal traslladar TFM sencer ni les seves sortides antigues.

Al servidor, des del checkout actualitzat, amb els dos fitxers a `transfer/`:

```bash
git pull --ff-only
(cd transfer && sha256sum -c calibration-transfer-v1.tar.sha256)
mkdir -p data/calibration-v1
tar -xf transfer/calibration-transfer-v1.tar -C data/calibration-v1
```

Extreure sobre una carpeta nova. L'executor verifica que `corpus.json` del paquet
coincideixi amb el del repositori i comprova els hashes dels inputs seleccionats.

## Servidor Linux amb NVIDIA

Prerequisits: Docker, driver NVIDIA i NVIDIA Container Toolkit amb exposició de
GPU a Docker. El target GPU utilitza Python 3.11, Torch 2.5.1/Torchvision 0.20.1
CUDA 12.4, Ultralytics 8.3.114 i els backends fixats del projecte. La disponibilitat
de les wheels i la compatibilitat amb la GPU concreta s'han de comprovar al servidor.

Les dependències directes estan fixades. Les transitives es resolen en construir
la imatge i es registren amb `pip freeze`; no es declara un lock complet de CUDA.
Conservar la imatge construïda per repetir el mateix estudi. Cada run registra
les versions efectives, el codi Python real, els inputs i el dispositiu.

Primera comprovació, sense inferir els clips:

```bash
bash benchmarks/calibration/run-server.sh --check
```

El script construeix la imatge i executa el preflight. Comprova pesos, versions,
FFmpeg, CUDA i un kernel NMS de torchvision real. La inferència posterior s'executa
**sense xarxa**, amb les dades muntades en lectura. Si CUDA falla, no passa a CPU
silenciosament. La primera construcció sí que necessita xarxa per a dependències.

Prova inicial de tres vídeos i una sola combinació:

```bash
bash benchmarks/calibration/run-server.sh --suite smoke --detector yolov8m-conf005-nms070 --tracker botsort-reid --output /results/smoke-v1
```

La comanda de la bateria pilot és:

```bash
bash benchmarks/calibration/run-server.sh --suite pilot
```

Per reprendre **la mateixa** bateria després d'una interrupció:

```bash
bash benchmarks/calibration/run-server.sh --suite pilot --resume
```

Per ampliar a tots els vídeos, iniciar un run diferent:

```bash
bash benchmarks/calibration/run-server.sh --suite all --output /results/all-v1
```

Els límits de recursos són configurables abans de la comanda:

```bash
CALIBRATION_GPU=1 CALIBRATION_CPUS=12 bash benchmarks/calibration/run-server.sh --suite pilot
```

`CALIBRATION_CPUS` és un enter 1–64, usat com a quota Docker i nombre de fils
Torch. `CALIBRATION_GPU` identifica la GPU física exposada; dins del contenidor
s'utilitza `cuda:0`. També s'admeten `CALIBRATION_DATASET`, `CALIBRATION_RESULTS`
(carpetes absolutes) i `CALIBRATION_IMAGE`. Les sortides per defecte són
`runs/calibration/screen-v1/` al host. El codi del benchmark és a la imatge;
el script s'ha d'executar des del checkout del servidor, no des de dins d'un altre contenidor.

## Disseny dels experiments

`experiment.json` defineix sis variants de detector:

- YOLOv8n i YOLOv8m, confiances 0,02 i 0,05, NMS IoU 0,7.
- Control YOLOv8m 0,05 amb NMS IoU 0,5.
- Control YOLOv8m 0,05/NMS 0,7 amb les 20 caixes més grans.

Totes utilitzen `imgsz=1280`, resize extern 1,5, classe persona, `max_det=300`,
FP32, `rect=True` i cap augmentació. Els controls de NMS i top20 canvien una
opció respecte de YOLOv8m 0,05/NMS 0,7. Els floats originals i la inversa exacta
del resize es conserven; no s'afirma igualtat de coordenades amb el CSV antic
de TFM, que truncava a enters. Nous models requereixen pesos identificats al
corpus i un adaptador compatible, no només un nom arbitrari.

Cada variant genera deteccions noves. Les mateixes caixes es reprodueixen amb
OC-SORT, ByteTrack, BoT-SORT i BoT-SORT+OSNet. No s'atribueix a ReID una diferència
que també canviï el detector. Les confiances del detector i les del tracker són
paràmetres diferents. Els paràmetres/semàntica propis de cada backend es preserven.

La suite pilot completa són **108 passades de detector i 432 de tracking**;
`all` són 564 i 2.256. No es genera MP4 per defecte. Les traces i descriptors
poden ocupar molt més que els 305 MiB d'entrada: fer primer smoke/pilot i mesurar
l'espai real abans d'all. Els treballs són seqüencials, amb fils CPU configurables;
no és una prova de concurrència de l'API ni un benchmark d'inferència batched.

Per estudiar després la confiança forta i la retenció mantenint el detector fix:

```bash
bash benchmarks/calibration/run-server.sh --experiment benchmarks/calibration/tracker-sensitivity.json --suite pilot --output /results/tracker-sensitivity-v1
```

Aquesta segona matriu compara BoT-SORT+ReID amb confiança forta 0,05/0,10/0,20
i retenció nominal 0,25/0,50/1 s. La confiança feble queda a 0,02. No representa
encara una cerca exhaustiva. El candidat final s'haurà de tornar a contrastar
amb vídeos/referències reservats i combinacions finals de detector i tracker.

Per veure el pla sense importar models, també es pot executar amb el paquet
actual instal·lat en un entorn local lleuger:

```bash
python -B benchmarks/calibration/run.py --dry-run
```

## Represa, resultats i mesures

Cada run té `run.json`, `events.jsonl`, `summary.json` i `summary.csv`.
Els subdirectoris `detections/` i `tracking/` contenen intents numerats,
configuracions efectives, CSV, informes i traces JSONL. El fitxer `completed.json`
es publica quan els artefactes d'aquell treball són complets i tenen checksums.
Un intent parcial no és un èxit. Un error individual no atura els altres casos;
la comanda acaba amb codi 1 si hi ha fallades.

`--resume` verifica els artefactes abans de saltar treballs complets i crea
un nou intent per als incomplets. No s'accepten canvis de codi, inputs, perfils,
referències, dispositiu o runtime dins del mateix run. Els resultats corruptes
s'assenyalen i no es reparen silenciosament. Un bloqueig del sistema operatiu
impedeix dos executors simultanis sobre el mateix run i s'allibera en morir el procés.

Les mesures inclouen temps de detector, temps de tracking+aparença/exportació,
CPU consumida, RSS mostrejada cada 0,2 s i pics CUDA assignats/reservats del procés.
No són ús global del servidor ni una mesura contínua d'utilització de GPU.
El detector separa decode/resize/predict/CSV. Els temps inclouen càrrega freda
del model; el tracking hereta el cas d'ús actual i no separa internament ReID
d'associació. Els hits/misses i candidats inferits del cache són explícits:
comparar temps amb la mateixa política de cache. El cache només es reutilitza
quan vídeo, caixes, model i preprocessament coincideixen.

Els IDs/fragments/observacions totals són de **tots els actors**, no del gimnasta.
Les prediccions són diferents de les observacions. L'estat del tracker es reinicia
per vídeo/variant i sempre s'executa el vídeo complet des del frame zero.

`--overlay` genera MP4 verificat per cada treball i inclou la codificació al temps.
Usar-lo en un run nou i filtrat amb `--case`, `--detector` i `--tracker` per revisar
finalistes. No comparar aquests temps directament amb runs sense overlay.

## Referències per comparar qualitat

El paquet de vídeos **no conté ground truth d'identitat independent**. Sense
referències revisades, `reference_status=not_evaluated` i les mètriques del
gimnasta són buides. No hi ha ranking automàtic ni HOTA/IDF1/MOTA inventades.

Crear plantilles locals, sense sobreescriure anotacions anteriors:

```bash
python -B benchmarks/calibration/reference_templates.py --suite pilot --output data/calibration-annotations-v1
```

Cada fitxer identifica el vídeo per SHA-256 i té `status=draft`. Cal revisar
el vídeo original, indicar `reviewer`, canviar a `reviewed` i completar mostres:

```json
{"frame_index": 430, "state": "visible", "bbox_xyxy": [210, 180, 360, 420]}
```

Les coordenades són un exemple de format, no una anotació real. `bbox_xyxy` és
en píxels originals. Els estats `occluded`, `out_of_frame` i `ambiguous` tenen
caixa null i s'exclouen de la mètrica principal; cal informar-ne el nombre.
Afegir finestres denses a inversions, contactes i pèrdues: cinc mostres d'una
plantilla no validen una rutina completa.

Per utilitzar referències revisades en una bateria nova:

```bash
CALIBRATION_ANNOTATIONS="$PWD/data/calibration-annotations-v1" bash benchmarks/calibration/run-server.sh --suite pilot --output /results/annotated-v1
```

L'avaluació compara caixes amb IoU ≥ 0,5 i compta disponibilitat del detector,
matches observats, IDs als matches, duplicats i canvis entre matches revisats.
Escull el match de màxim IoU per instant; pot alternar entre duplicats.
No és tracking seleccionat automàticament, puresa d'actor ni una mètrica MOT
exhaustiva. Les referències no entren al detector ni al tracker. Aquest esquema
permet comparar detectors diferents perquè no referencia els seus detection_id.

La [mostra d'anotació visual d'IA](annotation-pilot/README.md) afegeix 72 frames
de tres vídeos, amb 61 caixes provisionals i 11 casos ambigus/ocults. No són
ground truth humà. Per defecte s'ometen; `--allow-provisional-references` habilita
una comparació exploratòria marcada `evaluated_provisional_sparse`, preservant
la procedència del model. La galeria local permet revisar original i proposta.

## Verificació del banc

Les proves pròpies són a `benchmarks/calibration/tests`, separades dels tests
del paquet perquè no afegeixen dependències als runtimes CPU habituals.
Inclouen còpia, hashes, travessia de rutes, bloqueig, represa, intents fallits,
geometria de resize, referències independents i vídeo sintètic amb OC-SORT real.
La inferència YOLO real s'activa amb `CALIBRATION_TEST_WEIGHTS` local; sense
aquest valor només aquella prova s'omet explícitament.

```bash
docker build --target validation -f benchmarks/calibration/Dockerfile -t trampoline-vision:calibration-validation-v1 .
docker run --rm trampoline-vision:calibration-validation-v1 discover -s benchmarks/calibration/tests -v
```

El target `validation` reutilitza una imatge CPU local prèvia, configurable
amb `--build-arg VALIDATION_BASE=...`; no és la imatge que cal construir al
servidor. `run-server.sh` sempre construeix el target `gpu` des de Python oficial.
L'estat i els límits de la verificació d'aquest equip es registren a `validation.json`.

Per verificar també tot el metratge al servidor (dins de la imatge, amb dades
muntades a `/data` i sortides a `/results`):

```bash
python benchmarks/calibration/verify_corpus.py --dataset /data --full-decode --output /results/corpus-validation.json
```

La compatibilitat i el rendiment reals de CUDA queden pendents de la primera
execució al servidor. La qualitat física de les identitats queda pendent de
les anotacions i revisió independents; els tests de programari no la substitueixen.
