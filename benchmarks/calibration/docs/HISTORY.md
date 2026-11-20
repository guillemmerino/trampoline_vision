# Una comanda, una iteració i una revisió independent

Historial del disseny de les proves. [Estat actual](STATE.md) ·
[Comandes habituals i estructura](../README.md).

## Preparació espacial posterior al calibratge del detector

L’[estudi consolidat de preparació](BOX_PREPARATION_STUDIES.md) recull els
controls inicials de supressió, la implementació conservadora, la contenció,
els ancoratges amb densitat/residuals i les regions febles derivades. Inclou
els resultats congelats, les diferències de criteri i el protocol pendent
per comparar identitats temporals. Les simulacions posteriors continuen
fora del paquet; no s’han convertit en defaults ni en una prova de tracking.

## Revisió humana interactiva de les caixes

La [pàgina de revisió humana](HUMAN_REVIEW.md) permet aprovar o rebutjar
anotacions i candidates de YOLO, corregir caixes i incorporar casos visibles
sense anotació. Inclou els 1.440 frames i les dues confiances.

```bash
python3 -B -m benchmarks.calibration review serve
```

Obre `http://localhost:8766/` (reenvia el port si uses SSH). Les decisions
es desen a `runs/calibration/expanded-localization-v1/human-review/review-state.json`.
La mateixa eina permet recalcular després amb `assess`, sense repetir inferència
ni sobreescriure els resultats anteriors. [Ús, exportació i revaloració](HUMAN_REVIEW.md).

## Ampliació revisada: 18 vídeos, candidat 0,001 i control 0,002

```bash
cd /home/tics/personal/trampoline-vision
bash benchmarks/calibration/commands/run-expanded-localization.sh
```

El pla nou és `iterations/04-expanded-localization.json`: **18 vídeos sencers,
36 passades de detector i zero trackers**. No retoca paràmetres: comprova
si la localització amb els dos llindars fixats es manté en més exemples.
**Executada i revisada el 30-10-2026: 36/36 passades correctes.** Sobre les
àncores uniformes visibles: 721/760 amb 0,001 i 709/760 amb 0,002. Sobre tots
els instants visibles seleccionats: 1.204/1.267 i 1.185/1.267. 0,001 aporta 19
instants més sense cap pèrdua observada; genera un 23,09% més de caixes.
Es manté com a candidat principal. Els 61 casos `needs_review` no equivalen
automàticament a absència del gimnasta: inclouen fragments i discrepàncies
geomètriques. No s’han canviat paràmetres ni iniciat més proves.

[Informe de revisió, resultats per vídeo i pas següent](../../../runs/calibration/expanded-localization-v1/assessment/ASSESSMENT.md)
· [Galeria filtrada](../../../runs/calibration/expanded-localization-v1/assessment/index.html).
Les referències d’IA continuen provisionals i acceptades per a l’estudi;
els resultats reservats ja han estat consultats i la reserva no és intacta.

S’han preparat **1.440 fotogrames anotats (80 per vídeo)**, amb 1.267 caixes
visibles i 173 exclusions explícites. Les 72 mostres antigues conserven
geometria/estat. Les referències d’IA estan acceptades per a l’estudi i mantenen
`provisional`, `reviewer_type=model` i `human_reviewed=false`.

Hi ha 12 vídeos de desenvolupament i 6 de reserva temporal, de la mateixa
captura i sense identitats verificades. S’informa separadament la cobertura
sobre àncores uniformes (resum principal), finestres denses i mostres antigues.
No és un holdout independent ni una anotació exhaustiva de tots els frames.

La selecció substitueix AGE2 `001925_21.0` per `002952_23.0`, perquè en les
12 imatges de resum del primer no es veia cap exercici. El corpus històric
no es modifica. [Selecció, procedència i comandes detallades](../annotations/expanded-v1/README.md).

Per revisar els resultats en una conversa independent, cal començar per
`runs/calibration/expanded-localization-v1/REVIEW.md`. El paquet inclou inputs
congelats, CSV, mètriques per vídeo/partició/estrat i galeria de 1.440 làmines.
No genera MP4: és una prova de detector. RAM, VRAM i temps del detector es
registren; el renderitzat de làmines es mesura separadament.

El mateix wrapper admet `--dry-run` (validació sense inferència) i `--resume`.
Per reconstruir/verificar la revisió sense GPU ni originals:

```bash
python3 -B -m benchmarks.calibration iterate \
  --output runs/calibration/expanded-localization-v1 --review-only
```

## Què vol dir «mostra»

Una mostra és **un fotograma concret anotat**, no un vídeo. Els tres vídeos
de la primera prova es processen sencers: 930 + 1110 + 570 = 2610 fotogrames.
Les anotacions existents cobreixen 24 instants de cada vídeo: 72 en total.
En 61 el gimnasta es considera visible i té una caixa de referència; els altres
11 són ambigus/ocults i no entren a la mètrica principal.

«Caixa compatible en 48/61» vol dir que, en 48 d’aquests 61 fotogrames,
YOLO ha produït almenys una caixa de persona amb IoU ≥0,5 respecte de la caixa
anotada del gimnasta. És una mesura sobre fotogrames seleccionats, no una
proporció de vídeos ni de tots els fotogrames de les rutines.

Les caixes actuals són d’IA i **l’usuari les ha acceptat com a referència per a
aquest estudi**. Es conserva la procedència original: aquesta acceptació no
afirma una inspecció humana independent de totes les mostres. Els informes
històrics es mantenen intactes. Les exclusions continuen explícites.

## Configuració fixada: 0,001 principal i 0,002 control

El pla anterior és `iterations/03-localization-candidates.json`, amb la matriu
`iterations/localization-candidates-experiment.json`: només dues variants de
YOLOv8m, **0,001 principal** i **0,002 control**, NMS 0,7 i max_det=300 fixos.
`run-localization.sh` selecciona aquest pla i output propi. Els executables i
plans de les dues proves anteriors es conserven per reproducció.

Aquest executable conserva l’abast de tres vídeos (6 passades de detector,
zero trackers). Per ampliar la mostra cal usar el pla 04 i
`run-expanded-localization.sh`, descrit més amunt; no s’ha canviat l’abast
del pla 03 ni el resultat de les proves anteriors.

### Revisió de localització, separada de l’IoU

`detection_review.py` publica simultàniament les mètriques geomètriques originals
i una classificació d’utilitat a `samples.csv` i `review.json`:

- `sufficient`: caixa amb IoU ≥0,5, o candidata acceptada explícitament per revisió.
- `partial`: caixa parcial conservada com a candidata per a associació posterior,
  amb `partial_bbox=true`. No es dedueix automàticament de confiança baixa.
- `absent_or_incorrect`: no hi ha deteccions o una revisió rebutja la candidata.
- `needs_review`: hi ha caixes però cap supera el criteri geomètric i no hi ha
  decisió explícita. No es converteix automàticament en fallada ni en parcial.
- `excluded`: referència oculta/ambigua, fora del denominador de cobertura.

La classificació no modifica coordenades, confiança, IoU, referències, models,
tracking ni flags del producte. `association_candidate_available` és evidència
d’avaluació, no una associació al gimnasta executada pel tracker.

El registre `annotation-pilot/localization-decisions-v1.json` conserva la
instrucció d’acceptació de les referències d’IA i les decisions sobre les
candidates concretes a 0,001/0,002:

- AGE 2 f0: localització suficient per decisió de l’usuari, IoU 0,483 intacte.
- AGE 3 f180: candidata parcial de cap, encara sense caixa suficient del cos.

Cada decisió es vincula a SHA del vídeo/referència/model, configuració del
detector i coordenades/confiança exactes de la candidata. Si els inputs o la
caixa canvien, la revisió falla en lloc d’aplicar una etiqueta a una altra caixa.
El número `det_id` és només local al frame; no s’utilitza com a identitat temporal.

Les decisions i l’acceptació es congelen a `inputs/localization-decisions.json`
en cada nova iteració. Els canvis de revisió formen part de la identitat i no
permeten reprendre silenciosament un run amb etiquetes diferents. La revisió
posterior pot fer-se amb `--review-only`, sense models ni vídeos originals.

Els resultats geomètrics de la prova anterior continuen sent **59/61** a 0,001
i 0,002. Aplicant les dues decisions, són **60 suficients + 1 parcial**; el
parcial no es compta com una caixa suficient ni s’afegeix al recompte d’IoU ≥0,5.

La reanàlisi dels CSV ja existents és a
`runs/calibration/localization-accepted-review-v1/REVIEW.md`. No ha repetit
inferència; les làmines font i els informes originals no s’han modificat.

L’ampliació d’anotacions ja està preparada a `annotation-expanded-v1/`.
L’execució posterior de les 36 passades queda a càrrec de la comanda del pla 04.

## Segona prova — només YOLO amb llindars més baixos

Després de la prova robusta, el tall 0,01 donava caixa compatible en **56/61**
fotogrames visibles anotats. Ara prioritzem disponibilitat de caixes i deixem
la coherència d’IDs i la duplicació per a mòduls posteriors.

```bash
cd /home/tics/personal/trampoline-vision
bash benchmarks/calibration/commands/run-low-thresholds.sh
```

Aquest **segon executable** selecciona el pla `iterations/02-low-detector-thresholds.json`:

- YOLOv8m amb **0,01 / 0,005 / 0,002 / 0,001** sobre els mateixos tres vídeos
  complets: **12 passades de detector i cap de tracking**.
- NMS 0,7, `imgsz=1280`, resize 1,5, FP32 i `max_det=300` fixos; sense top20.
- Sense trackers, ReID, prediccions temporals ni recovery offline. No es
  generen MP4; es conserven els CSV complets i es renderitzen **72 làmines**
  dels fotogrames anotats, cadascuna amb les quatre confiances. S’inclouen
  els 11 casos exclosos, marcats com a no avaluats.
- Mètrica principal: en quants dels 61 frames visibles hi ha almenys una
  caixa compatible amb el gimnasta. També registra caixes totals, duplicats
  espacials, IoU/confiança per mostra, RAM, VRAM i temps.
- Registra quants frames de tot el vídeo arriben a `max_det=300` i el màxim
  de caixes retornades per frame. Arribar al cap indica possible truncament;
  no prova que s’hagi descartat el gimnasta. No s’augmenta el cap silenciosament.
- Les referències d’IA continuen provisionals, pendents de validació humana.

En acabar, l’agent d’una conversa nova ha de llegir:

```text
runs/calibration/low-detector-thresholds-v1/REVIEW.md
```

La carpeta conté `inputs/` congelats, `run/detections/` amb CSV/checkpoints,
`review/summary.csv`, `review/samples.csv`, `review/review.json` i
`review/index.html` amb les làmines `review/images/`. Conserva la carpeta
sencera. No necessita els originals per fer la revisió posterior; el renderitzat
inicial de les làmines sí que llegeix els vídeos locals verificats.

El temps del detector inclou càrrega, decode/resize/inferència/CSV. La generació
de làmines es mesura separadament (`sample_render_elapsed_s`); no és temps de
tracking ni de codificació MP4. No hi ha cache de descriptors d’aparença.

Per reprendre una interrupció, amb el mateix codi/pla/inputs/runtime:

```bash
bash benchmarks/calibration/commands/run-low-thresholds.sh --resume
```

Per veure només el pla, sense inferència:

```bash
bash benchmarks/calibration/commands/run-low-thresholds.sh --dry-run
```

Per reconstruir/verificar la revisió, sense models, GPU ni originals:

```bash
python3 -B -m benchmarks.calibration iterate \
  --output runs/calibration/low-detector-thresholds-v1 --review-only
```

Prompt de revisió: «Llegeix `runs/calibration/low-detector-thresholds-v1/REVIEW.md`.
Compara les quatre confiances respecte de 0,01, revisa els frames recuperats
i els encara absents a la galeria, i comprova possible saturació de max_det.
Prioritza localització del gimnasta. No avaluïs IDs ni declaris validació humana.»

## Primera prova robusta de llindar — executable original

Des del servidor:

```bash
cd /home/tics/personal/trampoline-vision
bash benchmarks/calibration/commands/run-iteration.sh
```

La comanda construeix la imatge, verifica inputs/referències i kernels CUDA,
executa el pla i genera el paquet de revisió. La inferència s’executa amb
Docker sense xarxa, dades/referències en lectura i els pesos locals verificats.

El pla per defecte és `iterations/01-threshold-robustness.json`, amb la matriu
`iterations/threshold-robustness-experiment.json`. El títol **Prova robusta de llindar**
queda registrat al pla, a `iteration.json` i a l’informe de revisió:

- Els mateixos tres vídeos, complets i des del frame zero.
- YOLOv8m, confiança **0,01 / 0,02 / 0,05 / 0,10**, mateix NMS 0,7 i resta d’opcions.
- OC-SORT, ByteTrack i BoT-SORT amb/sense ReID. Confiança forta **0,10**,
  confirmació **3** i retenció nominal **0,5 s**, fixes en totes les variants.
- ByteTrack i els dos BoT-SORT usen admissió feble **0,01** en aquesta matriu
  per poder consumir les noves caixes. És un override experimental comú als
  quatre llindars; els perfils globals conserven 0,02. OC-SORT no incorpora
  una passada feble. Amb detector 0,10, el pool feble desapareix: és el
  control restrictiu de la prova.
- **12 passades de detector i 48 de tracking amb MP4**. Les deteccions de cada
  vídeo/variant es comparteixen entre els quatre trackers.
- Referències provisionals explícitament habilitades; recovery offline absent.

La hipòtesi és comparar si els talls més baixos aporten caixes útils als instants
on faltaven, i si el tall més alt redueix confusions, mesurant també la
continuïtat del gimnasta. No s’assumeix que un llindar sigui millor. El nom
identifica l’exploració dels llindars; les anotacions provisionals encara
no permeten declarar una configuració òptima validada. El resultat no canvia cap configuració per defecte automàticament.
El pla fixa el nombre de treballs; si es resol un abast diferent, l’executor
s’atura. Afegir vídeos sense referències acceptades també és un error.

Per veure el pla sense inferència (ni imports de models):

```bash
PYTHONPATH="$PWD/src" python3 -B -m benchmarks.calibration iterate --dry-run
```

Per reprendre una interrupció amb el mateix codi, pla, inputs i runtime:

```bash
bash benchmarks/calibration/commands/run-iteration.sh --resume
```

Un output existent no es sobreescriu. Per una iteració nova, usar un altre pla
i un altre nom, per exemple `--plan benchmarks/calibration/config/iterations/05-tracking.json
--output /results/iteration-02` quan aquest pla s’hagi preparat després de revisar
l’anterior. No s’han creat ni executat plans posteriors en aquest increment.

## Què queda en acabar

Per defecte, la carpeta del host és `runs/calibration/threshold-robustness-v1/`:

```text
threshold-robustness-v1/
  REVIEW.md                  # Punt d’entrada per a una conversa nova
  iteration.json             # Estat, abast i hashes dels snapshots
  execution.log              # Progrés i errors del preflight/bateria
  preflight.json             # Dispositiu i versions efectives
  inputs/
    iteration-plan.json      # Hipòtesi, casos, variants i pressupost de treballs
    corpus.json
    experiment.json
    profiles.json
    run.json                 # Configuracions efectives, runtime i hashes de codi
    references/*.json        # Referències congelades amb tota la procedència
  run/
    run.json
    events.jsonl
    summary.json / summary.csv
    detections/              # CSV i metadades amb checksums
    tracking/                # Traces, avaluacions i MP4 amb checksums
    appearance-cache/
  review/
    review.json              # Estat tècnic, mètriques i identitat de l’anàlisi
    summary.csv              # Qualitat, temps, RAM, VRAM, cache i MP4 per treball
    samples.csv              # Fotograma/temps, matches i IDs observats/predits
    evaluations.json         # Avaluació i procedència de les referències
    index.html               # Galeria dels MP4
    checksums.json           # Checksums dels informes i snapshots
```

Cal conservar/moure **la carpeta sencera**, perquè els MP4 i traces són dins
`run/`. Els enllaços de l’informe són relatius. La revisió no necessita l’historial
del xat ni els vídeos/pesos originals. Les fallades produeixen estat incomplet
i codi de sortida no zero; «ready_for_review» acredita execució tècnica,
no qualitat suficient del tracking.

`CALIBRATION_RESULTS` pot canviar l’arrel del host (ruta absoluta). `/results`
és la ruta interna del contenidor. Es mantenen les variables de GPU, CPU,
dataset i imatge descrites al README del banc.

## Encàrrec per a l’agent d’una conversa nova

```text
Treballa a /home/tics/personal/trampoline-vision.
Revisa runs/calibration/threshold-robustness-v1/REVIEW.md com una iteració independent.
Comprova la integritat i l’estat tècnic. Compara 0,01/0,02/0,05/0,10 per vídeo i
tracker, revisa les incidències als MP4 i diferencia observacions/prediccions.
Explica què millora i què empitjora en la identitat del gimnasta.
Prepara una hipòtesi i un pla concret per a la següent iteració.
Conserva que les anotacions d’IA estan pendents de validació humana.
```

Es pot reconstruir/verificar el paquet sense Docker, GPU ni models, des del
checkout, amb biblioteca estàndard Python:

```bash
python3 -B -m benchmarks.calibration iterate --output runs/calibration/threshold-robustness-v1 --review-only
```

Aquesta operació verifica snapshots i artefactes abans de recalcular els
informes. No torna a executar el detector/tracker ni canvia les seves traces.
La versió del codi d’anàlisi queda registrada al resultat.

També es pot crear un paquet de revisió per a un run anterior, en una carpeta
nova, sense repetir inferència:

```bash
python3 -B -m benchmarks.calibration report \
  --run runs/calibration/server-rtx5070-v1 \
  --annotations benchmarks/calibration/annotations/pilot-v1/references \
  --output runs/calibration/review-baseline
```

En aquest darrer cas els MP4 continuen al run original; cal conservar-lo.

## Què mira la revisió i com continuem

La revisió separa disponibilitat de caixes, matches amb qualsevol ID, cobertura
amb un ID fix, canvis entre matches, prediccions i duplicats. El millor ID fix
s’escull a posteriori i és una mesura optimista de la mostra, no un selector del
gimnasta ni una garantia de puresa entre mostres. També es registra l’ID del
primer match i quantes observacions revisades conserva sense reescollir-lo.

Després d’aquesta iteració, la decisió següent dependrà dels resultats:

- Comparar els quatre llindars en caixes útils, continuïtat i contaminació.
  El volum total de deteccions no determina el guanyador.
- Fixar el detector candidat i preparar la comparació de confiança forta,
  feble i retenció del tracker, amb el control sense ReID. Els llindars del
  detector i tracker han de permetre que arribin les caixes febles.
- Després estudiar confirmació i llindars geomètrics/aparença dels candidats.
- Ampliar al pilot de 18 amb anotacions revisades i casos reservats. Els 94 no
  s’executen automàticament. Per fonamentar una configuració final cal més
  cobertura d’anotació i validació independent, no només executar més vídeos.

Aquest recorregut prepara experiments revisables; no garanteix que una sola
execució trobi l’òptim ni certifica anotacions provisionals.

## Fitxers de la implementació

- `iterations/01-threshold-robustness.json`: pla per defecte, nom i abast de la prova.
- `iterations/threshold-robustness-experiment.json`: quatre detectors i overrides experimentals del llindar feble.
- `iterate.py`: validació d’abast/referències, snapshots, estat, represa i revisió.
- `review.py`: verificació i informe autònom, també sobre runs anteriors.
- `evaluation.py`: mètriques d’ID fix i observacions/prediccions separades.
- `run.py`: exportació de les noves mètriques al resum del banc.
- `run-iteration.sh` i `run-server.sh`: entrada d’una comanda al servidor.
- `Dockerfile`: dependències en una capa reutilitzable quan canvien codi/plans.
- `tests/test_iteration.py`: ID fix amb duplicats, paquet transportable sense
  originals, errors/represa i rebuig de corrupció o canvis de pla.

El pla anterior `iterations/01-detector-confidence.json` es conserva per a
execució explícita amb `--plan` i un output propi. La comanda sense arguments
executa ara la prova robusta de quatre llindars.

Els perfils `configs/trackers/*.json`, `experiment.json`, pesos i referències
existents no es modifiquen per aquesta iteració.

La segona prova afegeix `detection_review.py`, l’opció `--detector-only` del banc,
els dos JSON de llindars baixos i `run-low-thresholds.sh`. El pla i l’executable
originals de la primera prova es conserven.
