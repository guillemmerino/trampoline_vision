# Protocol de continuïtat d’identitat v1

Estat: protocol preparat; bateria pendent. El [pla executable](identity-continuity-v1.json)
fixa els hashes de preparació, perfils i CSV. Objectiu: mantenir l’ID associat
al gimnasta acceptant mida variable, marge i fragments identificables. Cap
esquelet, selector automàtic del gimnasta o reunificació posterior d’IDs.

## Antecedents revisats i hipòtesi

- [Estudi 05](../../../../docs/26-reid-tracking-comparison.md): BoT-SORT + ReID
  redueix els canvis mínims entre instants revisats, però també perd algunes
  observacions i falla després de contactes. Les referències són disperses,
  amb una revisió posterior als resultats. Inclou AGE1 001814 com a segon cas,
  diferent d’AGE2 000709 d’aquest protocol, i deteccions anteriors.
- [Integració configurable](../../../../docs/27-configurable-box-tracking.md):
  quatre perfils, observacions i prediccions separades, cache d’aparença i MP4.
  Les comprovacions de regressió acrediten integració, no identitat correcta.
- [Arxiu de preparació](../../archive/detection-preparation-v1/README.md),
  especialment decisions, variants i zones: disponibilitat geomètrica i
  utilitat visual no són equivalents. AGE3 #97 ja manca de candidata clara;
  #180 i #510 il·lustren fragments útils. La zona central soft té evidència
  sobre mostres de 18 vídeos, sense validació temporal exhaustiva.

Hipòtesi prèvia: BoT-SORT + ReID és el candidat preferent, pendent de contrast.
El contrast amb BoT-SORT sense ReID aïlla l’aportació d’aparença. OC-SORT i
ByteTrack contrasten perfils complets: també canvia l’admissió d’evidència feble.
No s’atribuirà tota diferència a l’algoritme ni s’ajustaran llindars després
de mirar els resultats d’aquesta primera comparació.

## Entrada i matriu fixades

| Vídeo | Frames [inici, final) | Durada |
| --- | --- | --- |
| JPN_AGE_1_000905_31.0 | [0, 930) | 31 s |
| JPN_AGE_2_000709_37.0 | [0, 1110) | 37 s |
| JPN_AGE_3_001351_19.0 | [0, 570) | 19 s |

30 FPS, 960×1080; 2.610 frames font, 10.440 frames de tracking, quatre perfils
per vídeo. Sempre des de zero, fins al final, amb tots els actors; cap reset
en començar una finestra. Els IDs són locals a cada execució i perfil.

YOLOv8m enregistrat: confiança 0,001, NMS 0,7, imgsz 1280, resize 1,5,
max_det 300, float32, sense tall posterior per àrea. CSV complets del cache
`expanded-localization-v1/run/detections`, amb marcador de finalització,
hashes i procedència del detector verificats. Un cache absent o incompatible
és un error: no hi ha fallback d’inferència.

Preparació de producció `representative-boxes.json`: agrupament, regions,
contenció, silueta, fons medià fix retrospectiu de tot el vídeo, zona
`[0.06, 0.25, 0.94, 0.93]` soft i màxim 12. Es registra la configuració
efectiva amb tots els defaults i el codi. El fons retrospectiu és una limitació
per extrapolar a ús en directe. Cada perfil recalcula la mateixa preparació;
la publicació final exigeix igualtat exacta de candidates amb l’auditoria.

Perfils existents, sense overrides d’associació: confiança forta 0,10,
3 matches forts consecutius per confirmar, retenció nominal 0,5 s;
ByteTrack/BoT-SORT admeten febles a 0,02. BoT-SORT conserva càmera identitat
i el possible tick extra de retenció del backend. No es força un límit nou
ni es desactiva la recuperació nativa. No s’invoca cap mòdul `recovery`.
ReID: OSNet x0.25 MSMT17 preentrenat, SHA del corpus, CPU/4 fils;
cache nou dins del run, amb verificació de píxels, preparació i model pròpia
del servei d’aparença. Cap entrenament ni descàrrega.

## Una comanda, comprovació segura per defecte

Des de l’arrel:

```bash
bash benchmarks/calibration/commands/run-identity-comparison.sh
```

Només fa preflight: valida tots els CSV i vídeos, PTS/CFR, hashes, perfils,
pesos locals i imports/versions; no associa, prepara, extreu descriptors ni
genera MP4. Per a la iteració posterior autoritzada, la mateixa comanda amb
`--execute` inicia les 12 execucions. No executar-la en aquesta entrega.

Requisits: Docker i imatge local `trampoline-vision:calibration-gpu-v1`;
no cal GPU malgrat el nom de la imatge. Runtime fixat: Torch 2.7.1,
Torchvision 0.22.1, trackers 2.6.1, BoxMOT 16.0.9, psutil 7.0.0.
S’enregistra l’ID immutable de la imatge i totes les distribucions.
Contenidor sense xarxa, 4 CPU, 8 GiB RAM, shm 1 GiB; execucions seqüencials.
`CALIBRATION_DATASET`, `CALIBRATION_RESULTS`, `CALIBRATION_IMAGE` adapten els
mounts. Entrades de projecte/dataset només lectura; resultats a `/results`.
Per defecte sortida `runs/calibration/identity-continuity-v1`; si existeix,
s’atura. `--output /results/<nom-nou>` escull un altre destí, sense reprendre.
Canviar codi, pla o rutes exigeix un run nou.

El temps i la memòria encara no s’han mesurat amb aquest protocol. Es
registraran temps total i per vídeo, CPU user/system, màxim RSS del procés,
temps de cada perfil, comptadors i cost ReID/cache als informes de producció.
El temps de cada perfil inclou lectura, preparació, aparença i codificació;
no és un benchmark pur d’associació. El RSS no inclou fills ffprobe.
Reservar inicialment 10 GiB de disc i revisar el consum real després.

## Artefactes i revisió independent

- `inputs.json`: pla complet, hashes de codi/configuracions/corpus, configuració
  efectiva, entorn, models, metadades originals del detector i absència de recovery.
- Per vídeo, `case.json`, `preparation.jsonl`: font original completa amb
  procedència CSV, candidates derivades i auditoria de selecció/fusió/exclusió.
- `candidates.mp4`: totes les candidates amb ID local per frame, sense tracker.
- Per perfil, `<perfil>.frames.jsonl`, `<perfil>.json` i `<perfil>.mp4`:
  assignacions, estats, esdeveniments, candidates no assignades i motius;
  caixes observades contínues i prediccions discontínues, tots els actors.
  Cada MP4 es comprova amb ffprobe per recompte, dimensions i tots els temps.
- `summary.json` i `completed.json`: recursos i hashes d’artefactes científics
  incloent MP4; SQLite ReID queda fora del marcador. Sense marcador final,
  el run és incomplet i no pot alimentar conclusions comparatives.

Un altre agent ha de comprovar primer els hashes de `completed.json` amb
`engine.common.verify_artifacts`, obrir originals/candidates i després els
quatre MP4 sincronitzats pel número de frame (els overlays afegeixen capçalera).
No traslladar coordenades del MP4 a píxels originals sense treure la capçalera.
L’executor comprova que els quatre perfils han rebut les mateixes candidates.
Els IDs numèrics o colors entre perfils no indiquen la mateixa persona.

## Finestres contínues i mecanisme d’anotació

Primera passada independent de les sortides dels trackers: identificar el
gimnasta al vídeo original i anotar totes les candidates útils mirant
`candidates.mp4` i `preparation.jsonl`. Revisar **cada frame** dels intervals
següents; índex base zero i extrem final exclòs:

| Vídeo | Finestres | Frames únics |
| --- | --- | --- |
| AGE1 000905 | [0,150), [270,540), [780,930) | 570/930 |
| AGE2 000709 | [0,180), [450,660), [930,1110) | 570/1110 |
| AGE3 001351 | [0,210), [270,420), [450,570) | 480/570 |

Total inicial 1.620/2.610 frames (54/87 s). Inclou entrada, tram central,
final i els contraexemples coneguts d’AGE1 #300–390/#474–508 i AGE3 #97/#180/#510.
AGE2 és estratificació temporal prèvia, sense afirmar encara on té contactes.
No extrapolar aquestes finestres als 990 frames restants ni als 94 vídeos.

Desar decisions noves a `review/candidates.jsonl`, una línia per frame,
vinculada a `inputs.json` i al SHA de `preparation.jsonl`. Exemple de format
(IDs il·lustratius: copiar els reals de la traça):

```json
{"case_id":"JPN_AGE_3_001351_19.0","frame_index":180,"presence":"visible","useful_candidate_ids":["ID_REAL_A","ID_REAL_B"],"candidate_labels":{"ID_REAL_A":"gymnast_partial","ID_REAL_B":"mixed_useful"},"raw_useful_detection_ids":[],"raw_reviewed":false,"ambiguous_candidate_ids":[],"reviewer":"agent:nom","human_validated":false,"notes":"Fragment identificable; segona caixa inclou marge i assistent"}
```

Identificació pel moviment, vestimenta i context temporal del vídeo original;
una caixa mixta només és útil si permet localitzar inequívocament el gimnasta.
No imposar IoU ni cobertura de cos sencer. Admetre diverses candidates, fragments
i caixes àmplies; marcar `ambiguous` quan no sigui decidible. Cap anotació
implícita per propagació. Si no hi ha candidata útil, inspeccionar els originals
de l’auditoria i registrar `raw_reviewed:true` amb els IDs útils, si existeixen:
això separa manca a YOLO, exclusió de preparació i mera manca de revisió.
`useful_candidate_ids:[]` amb presència visible és absència confirmada de
candidata només després d’inspecció; amb presència ambigua és no avaluable.

Segona passada: obrir perfils en ordre fix i registrar a `review/tracks.jsonl`,
per frame/perfil, `gymnast_observed_ids`, `gymnast_predicted_ids`,
`assistant_ids`, `audience_ids`, `other_ids`, `ambiguous_track_ids`,
`reviewer`, `human_validated`, `notes`. Vincular també SHA de la traça i run_id.
Classificar visualment la persona de cada ID, incloent quan abandona el gimnasta.
Una predicció sobre l’assistent es marca com a tal, sense inventar candidata.
No escollir retrospectivament l’ID dominant com si fos selector automàtic.

Registrar a `review/events.jsonl` intervals [inici,final), perfil, ID abans i
després, tipus (`candidate_gap`, `association_gap`, `prediction_only`,
`id_change`, `same_id_return`, `transfer_assistant`, `transfer_audience`,
`ambiguous`), evidència de frames i notes. Una transferència exigeix veure el
mateix ID passar del gimnasta a una altra persona. Marge o contacte no basten.
Examinar també tots els altres actors: un ID antic pot seguir l’assistent
mentre el gimnasta rep un ID nou.

Després de congelar la primera anotació, ampliar amb finestres ±60 frames
al voltant de naixements, pèrdues, retorns, retirades, canvis de conjunts d’IDs
o sospites visuals en qualsevol perfil. Fusionar solapaments, limitar al vídeo,
conservar origen de selecció i separar aquestes finestres dirigides de les
prèviament fixades. No són una mostra aleatòria ni un denominador independent.
Una discontinuïtat als límits obliga a ampliar fins a observar-ne el context.
Les decisions d’agent continuen provisionals; només revisió humana explícita
pot posar `human_validated:true`, amb autor i data. L’actual UI de localització
dispersa no implementa aquest esquema temporal; aquí el mecanisme és MP4 +
JSONL auditable. No reutilitzar ni sobreescriure les decisions antigues.

## Lectura de resultats i criteri de decisió

Separar tres capes i conservar numeradors, denominadors i censura als extrems:

1. **Disponibilitat:** frames visibles decidibles amb ≥1 candidata útil /
   frames visibles decidibles revisats. Buits en originals, exclusions de
   preparació i ambigüitats separats. Cap diferència entre trackers és atribuïble
   a disponibilitat si l’entrada és idèntica.
2. **Associació:** frames amb observació de gimnasta / frames revisats amb
   candidata útil. Registrar candidates útils no assignades, no confirmades,
   sota llindar i associades a altres IDs; separar predicció sense mesura i
   buits sense cap sortida. No convertir naixement pendent en detecció absent.
3. **Identitat:** durades d’intervals continus correctes per ID, fragmentació,
   canvis confirmats, retorn del mateix ID, buits observacionals/predits i
   transferències a assistent/públic (nombre, durada i frames). Comparar frames
   decidibles comuns dels quatre perfils i informar també exclusions pròpies.

Amb duplicats simultanis, usar conjunts d’IDs acceptables i informar el mínim
de canvis compatible com a límit inferior, junt amb intervals de cada ID;
no penalitzar l’ordre arbitrari de dues candidates. Separar successions
observades consecutives, retorns després de buits i transicions entre finestres
no connectades. No comptar aquesta darrera categoria com a canvi temporal real.
Una predicció pot donar suport a continuïtat provisional, però no és observació
ni prova d’identitat durant una oclusió. Informar continuïtat observada i
continuïtat amb predicció revisada separadament.

Primer comparar contaminació/transferències, després longitud dels fragments
correctes i canvis, conjuntament amb cobertura observada condicionada a
candidata disponible. Menys canvis a costa de deixar de seguir el gimnasta
no és una victòria. Si hi ha compensacions, presentar Pareto i exemples,
sense forçar un guanyador. Resums per vídeo i totals amb denominadors;
cap IDF1/HOTA/MOTA global sense referència temporal adequada. Les anotacions
disperses actuals només són antecedent i índex de casos per revisar.

Tancament de la iteració següent: informe independent amb limitacions,
taula dels tres nivells, registre de decisions i una selecció petita de casos
visuals en Git. Traces, caches i MP4 a `runs/`. Qualsevol perfil preferit
continua experimental fins al contrast; no modificar defaults ni ampliar corpus.

## Comprovació d’aquesta entrega

2026-11-20: la comanda anterior ha retornat `preflight_passed` amb els tres
vídeos, 2.610 frames font i quatre perfils; `tracking_executed:false`,
`detector_inference:false`, `recovery:false`. Imatge local verificada:
`sha256:96f1796b900083d68831101bfc0a171685d5695d64547e4a226f0086017f64a7`.
No s’ha creat el run de la bateria. El preflight verifica inputs i runtime;
la generació completa de traces/MP4 i l’extracció ReID queden pendents de
l’execució posterior. Els controls sintètics de seguretat són a
`benchmarks/calibration/tests/test_identity_comparison.py`.
