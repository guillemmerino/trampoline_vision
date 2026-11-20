# 32. Avaluació del calibratge del tracker de caixes i següent estudi

26/10/2026. Revisió documental i reanàlisi de les traces de la prova curta.
No s’ha executat una nova bateria, ni canviat perfils o llindars.

**Lectura actual:** aquest document conserva els criteris i resultats de la
reanàlisi inicial. L’[objectiu vigent](../benchmarks/calibration/docs/STATE.md)
és mantenir l’ID del gimnasta amb caixes de suport que poden ampliar-se, i
reconstruir/associar els esquelets després. L’IoU≥0,5 dels recomptes històrics
no és un criteri suficient per acceptar o rebutjar aquestes ampliacions.
La primera preparació conservadora i els diagnòstics de cobertura ja són
executables; el calibratge i les mètriques temporals continuen pendents.

## Objectiu i frontera

L’objectiu és escollir una configuració fonamentada de detecció i tracking que
mantingui observacions del gimnasta amb una identitat coherent, abans del recovery
offline. Cal maximitzar cobertura correcta i continuïtat, controlant transferències
a assistents/jutges, duplicats, buits i cost. No hi ha un òptim universal demostrat:
cal una funció de decisió, dades de desenvolupament i validació reservada.

El tracking normal inclou moviment, ReID i reassociació d’un ID encara viu durant
`max_lost_s`. Aquest mecanisme és dins l’objecte d’estudi. La unió posterior de
fragments/IDs del paquet `recovery` queda fora de les mètriques i no s’activa.
No es poden reparar IDs abans d’avaluar el tracker.

YOLO classifica persones; el tracker manté múltiples identitats. Escollir quin
actor és el gimnasta és una política separada (`subjects`, encara pendent).
Avaluar la continuïtat del gimnasta amb referències és possible sense implementar
el selector, però no acredita selecció automàtica de subjecte.

## Documentació contrastada

- [07](07-tracking-and-subject-selection.md): identitat, observació/predicció i selector separat.
- [12](12-validation-strategy.md): criteris d’acceptació oberts, independència de dades i anotacions.
- [24](24-final-geometry-and-weak-evidence-diagnosis.md) i [25](25-independent-box-tracking-study.md): límit de caixes de pose i millora amb deteccions de persona independents.
- [26](26-reid-tracking-comparison.md): ReID com a candidat, no trajectòria completa validada; possibles caixes mixtes i transferències a jutges.
- [27](27-configurable-box-tracking.md): els quatre perfils parteixen de valors inicials pendents de calibrar.
- [31](31-server-calibration-benchmark.md) i [protocol del banc](../benchmarks/calibration/docs/SERVER.md): primera matriu de detectors i segona de sensibilitat, sense ranking automàtic.
- [Pilot 07](../benchmarks/studies/07-recovery-global/README.md): abaixar confiança forta de 0,10 a 0,05 va augmentar matches escassos, però també IDs/fragments. Aquelles anotacions i detectors no són equivalents a la prova nova; és un avís metodològic, no una comparació numèrica directa.

## Què ha aportat la prova curta

Execució `runs/calibration/server-rtx5070-v1/`: tres vídeos complets, 2610 frames,
87 segons, un detector `yolov8m-conf005-nms070` i quatre perfils. Deteccions
compartides per vídeo. No hi ha cap cerca de llindars en aquesta execució.

S’ha validat Docker/GPU RTX 5070, kernels i models amb Torch 2.7.1/CUDA 12.8,
i corregit el filtratge de classe amb Ultralytics 8.3.116. S’han completat 23
proves i 12 treballs amb MP4. És una base executable i auditable per calibrar.

Les referències són 72 instants, 61 visibles i 11 exclosos, proposats per IA i
**pendents de validació humana**. Són una mostra dirigida, escassa i amb intervals
ja coneguts; no són ground truth independent. Representen 72/2610 frames, sense
que aquesta proporció impliqui mostreig representatiu o independència.

| Perfil | Matches observats / 61 | Canvis entre matches, suma dels vídeos | Millor ID fix per vídeo, suma / 61 |
| --- | ---: | ---: | ---: |
| ocsort | 46/61 | 16 | 21/61 |
| bytetrack | 44/61 | 19 | 17/61 |
| botsort | 44/61 | 14 | 25/61 |
| botsort-reid | 46/61 | 12 | 29/61 |

La darrera columna és una reanàlisi offline: per cada vídeo es compten totes les
caixes observades de cada ID que superen IoU 0,5 amb la referència, incloent
alternatives duplicades; després s’escull retrospectivament el millor ID.
No uneix fragments, no canvia els resultats i no és un selector executable.
És una cota optimista de cobertura amb un ID fix als instants mostrejats;
no demostra puresa entre mostres. La suma no és un ID compartit entre vídeos.

Per ReID, el millor ID fix cobreix 13/19, 7/22 i 9/20 mostres, respectivament.
La mètrica anterior permetia 16/19, 16/22 i 14/20 perquè escollia un ID diferent
cada vegada. Això explica per què molts matches espacials encara no donen una
trajectòria única del gimnasta. A AGE 3 hi ha duplicats: comptar totes les caixes
compatibles d’un ID dóna 9 mostres per al millor ID, mentre que limitar-se als
matches guanyadors de màxim IoU en donaria 8.

El detector està disponible en 17/19, 16/22 i 15/20 mostres: **48/61 (78,7%)**.
Amb aquestes deteccions i caixes observades originals, aquesta és la cota màxima
de cobertura observada del protocol. Els altres 13 instants no es resolen
ajustant només associació o augmentant prediccions. No sabem encara si baixar
la confiança del detector els recuperarà o si són fallades de localització/NMS.

ReID obté 46/48 dels instants amb detecció disponible. Les altres dues mostres
són frame zero d’AGE 1 i AGE 3, amb confirmació inicial pendent. A les 48 mostres
amb detecció hi ha almenys una caixa compatible amb confiança ≥0,10. Això no
invalida l’associació feble entre àncores: els frames no anotats poden decidir
si un ID arriba viu a la mostra següent.

ReID redueix canvis respecte a BoT-SORT a AGE 1 (5→3) i AGE 2 (6→5), però a AGE 3
augmenten (3→4). Mantindria BoT-SORT±ReID com a candidats principals i OC-SORT/
ByteTrack com a controls. No descartaria cap backend només pels tres clips.
Tots els perfils han tingut només una configuració inicial.

Els IDs/fragments globals del banc inclouen espectadors i jutges; no són una
mesura de continuïtat del gimnasta. Un ID pot tenir matches correctes i també
caixes observades fora de la referència en altres instants. La reanàlisi en
registra els casos amb IoU <0,5; són desacords espacials per revisar, no proves
automàtiques de transferència d’actor.

## Deficiències concretes del disseny actual

1. **Mètrica orientada a qualsevol ID per instant.** Cal afegir cobertura d’un
   ID fix, continuïtat, contaminació i latència inicial. La reducció de canvis
   a costa de perdre observacions no ha de guanyar automàticament.
2. **Anotació insuficient.** Les inversions/contactes més difícils inclouen
   exclusions; també s’han de revisar. Les mostres disperses no mesuren durada
   dels buits ni tots els canvis d’identitat.
3. **Cap llindar s’ha variat en la prova executada.** No hem contrastat detector
   0,02/0,05, NMS 0,5/0,7, confiança forta/feble, retenció, confirmació ni gates
   d’associació/aparença. Els valors per defecte no queden calibrats pel resultat.
4. **La sensibilitat preparada és parcial.** `tracker-sensitivity.json` té 9
   variants només de ReID: confiança forta 0,05/0,10/0,20 × retenció 0,25/0,5/1 s.
   No varia confiança feble, confirmació ni llindars geomètrics/aparença, i no
   inclou el control equivalent sense ReID.
5. **Interacció entre llindars.** Amb detector 0,05, un tracker feble 0,02 no veu
   caixes 0,02–0,05. A la variant forta 0,05 del fitxer de sensibilitat, el pool
   feble pràcticament desapareix. Comparar fort/feble requereix un detector amb
   tall prou baix, per exemple 0,02, i combinacions vàlides `low < high`.
6. **Naixement i associació forta estan lligats.** L’adaptador BoT-SORT passa
   `confidence_threshold` tant a `track_high_thresh` com a `new_track_thresh`,
   i la confirmació de domini usa el mateix llindar. Separar admissió per
   mantenir un ID i confiança per crear-lo exigiria ampliar el perfil/codi,
   preservant els defaults anteriors per als controls.
7. **Semàntica específica del backend.** `match_thresh` i `proximity_thresh`
   de BoT-SORT operen sobre distàncies; no són el mateix que `min_iou` d’OC-SORT/
   ByteTrack. En BoxMOT 16.0.9, el gate de proximitat també limita on ReID pot
   ajudar; el llindar d’aparença s’aplica diferent a pools confirmats i pendents.
   Cal estudiar la implementació fixada, no traslladar valors d’una API latest.
8. **Sense selecció automàtica del gimnasta.** L’avaluador fa matching amb la
   referència a cada instant. No equival a una sortida d’un subjecte únic.

## Protocol recomanat

### 1. Congelar criteri de qualitat i mètriques

Avaluar només la sortida crua del tracker, sense unió offline d’IDs. Mesurar:

- Disponibilitat/localització del detector sobre el gimnasta visible.
- Cobertura observada amb un ID fix i dominant, explicitant que escollir-lo
  a posteriori és optimista. Afegir avaluació condicionada a una identificació
  inicial correcta: seleccionar l’ID una sola vegada en una àncora revisada,
  sense reescollir-lo després d’una pèrdua. Això és una política d’avaluació,
  no alimentar anotacions al detector/tracker ni acreditar el selector.
- Canvis d’actor, observacions del mateix ID sobre distractors i duplicats.
  Anotar assistents/jutges propers als moments conflictius per desambiguar
  contaminació i error de geometria; no cal anotar cada espectador per al
  protocol específic del gimnasta.
- Durada màxima i distribució de buits mentre el gimnasta és visible, fragments,
  longitud de trams observats correctes i recuperació després d’oclusió.
  Separar oclusió real, predicció temporal i detecció perduda amb actor visible.
- Latència inicial i cobertura estable per separat: la confirmació inicial
  no és un canvi d’actor, però també té cost i no s’ha d’amagar post hoc.
- Temps/RAM/VRAM, cold/warm cache i rendiment per vídeo i tipus d’incidència.

Prioritzar identitat correcta i cobertura amb continuïtat; fer servir cost per
escollir entre candidats de qualitat comparable. Fixar abans els límits
acceptables de contaminació, buits i cobertura; no inventar-los després de veure
qui guanya. Informar mitjanes per vídeo, pitjors casos i comparacions aparellades;
no tractar frames correlacionats com si fossin mostres independents.

IDF1/HOTA poden afegir-se amb les anotacions i protocol adequats. Executar una
mètrica MOT global sobre tots els trackers amb només el gimnasta anotat
penalitzaria actors legítims no etiquetats. Cal protocol de target amb distractors
ignorats o etiquetatge MOT complet. No derivar aquestes mètriques dels JSON
escassos actuals.

### 2. Ampliar a 18 vídeos, amb dades reservades

El `pilot` existent té 18 vídeos, sis per AGE i 9 min 36 s. És una ampliació
raonable abans dels 94. Proposta inicial: **12 de desenvolupament i 6 reservats**,
amb diversitat d’inversions, contactes, escala, blur, distància als assistents i
posició del panell. Els vídeos ja estudiats han d’anar a desenvolupament.

Fer el repartiment després de comprovar solapaments temporals i esportistes:
els grups correlacionats han d’anar junts. AGE no és una divisió independent
train/test. Si no es pot aconseguir separació de grups dins del pilot, ampliar
la selecció o declarar la validació com a interna. Tots els 94 vídeos pertanyen
al mateix context de competició/captura; més vídeos no demostren generalització
a altres competicions o càmeres.

Revisar humanament les caixes d’IA i exclusions, amb procedència/versionat.
Afegir mostreig distribuït i finestres denses fixades abans de mirar els
trackers. Per al contrast final, prioritzar trams complets densament anotats
(o vídeos sencers) dels reservats; només més àncores escasses no resolen les
mètriques de continuïtat. Conservar estats ocult/ambigu sense inventar caixes
ni esborrar els casos difícils segons el resultat.

### 3. Estudiar detector i després associació amb controls

- Fer el screening de les 6 variants de `experiment.json` sobre desenvolupament:
  n/m, confiança 0,02/0,05 i els controls de NMS/top20. Comparar abans la
  disponibilitat/localització del gimnasta i el cost; no només el nombre total
  de persones o fragments. La configuració executada és una referència.
- Escollir 2–3 candidats de detector per a l’experiment següent, sense proclamar
  òptim global. Contrastar els quatre trackers amb les mateixes deteccions.
  Conservar el control BoT-SORT sense ReID per atribuir l’efecte de l’aparença.
- Amb detector fix i tall baix compatible, començar per la matriu 3×3 de
  confiança forta/retenció, amb el control sense ReID. Després estudiar feble,
  confirmació i gates a prop dels candidats, amb combinacions vàlides.
- Exemples de rangs inicials, encara no calibrats: forta {0,05; 0,10; 0,20},
  retenció {0,25; 0,5; 1 s}, confirmació {1; 3; 5}, feble {0,02; 0,05} quan
  `low < high`. Per BoT-SORT, provar gates geomètrics/aparença i fusió de scores
  amb canvis controlats; no fer una graella cartesiana de tots els paràmetres.
- Després del cribratge separat, tornar a contrastar conjuntament els detectors
  i trackers finalistes: hi ha interaccions i una elecció seqüencial també pot
  perdre bones combinacions. Ajustar cada backend que es mantingui candidat;
  comparar defaults d’un amb un altre molt ajustat no demostra superioritat
  general de l’algoritme.
- Congelar 2–3 combinacions finals i avaluar-les als 6 vídeos reservats, amb
  mateix protocol. Qualsevol nou ajust sobre aquests resultats converteix
  aquest conjunt en desenvolupament i requereix una nova reserva.

### 4. Fer la cerca eficient

Executar les graelles sense `--overlay`; generar MP4 per als finalistes i
finestres problemàtiques. Compartir deteccions i descriptors entre perfils
compatibles. El cache ha de validar hashes, candidats, pesos i preprocessament.

El codi actual comparteix un detector entre trackers dins del mateix run i els
perfils ReID del mateix run comparteixen `output/appearance-cache`. Però la
identitat global del run entra a la signatura del detector, i cada output té
el seu cache. Una nova matriu amb output diferent no importa automàticament
les deteccions/cache de la prova anterior. Per evitar recalcular entre runs,
cal un import explícit verificat o opcions d’artefactes/cache compartits; no
saltant les comprovacions de `--resume`. El banc tampoc té encara un mode CLI
de detector sense tracker: el screening amb l’executor actual ha d’incloure un
perfil fix, o cal afegir aquest mode.

El cost observat de la prova actual és 58,34 s de detector + 391,77 s de tracking
amb vídeo. Escalant només per durada, els 18 vídeos amb un detector i quatre
perfils serien aproximadament **50 minuts amb overlays**. És una extrapolació
grossa de tres clips, no una mesura ni un pressupost de totes les matrius.
No hem mesurat aquesta bateria sense overlay i amb cache calent: fer una
comprovació curta abans d’estimar el cost real de la cerca.

Els 94 vídeos es reservarien per comprovar els finalistes i caracteritzar
fallades, després de congelar configuració i mètriques. Executar-los tots
ara amb molts paràmetres i les mateixes tres referències no fonamentaria un
òptim del gimnasta: en els altres 91 només tindríem diagnòstics de tots els actors.

## Estat resultant

BoT-SORT+ReID és un candidat justificat per continuar. La configuració
`yolov8m-conf005-nms070 + botsort-reid` és un baseline mesurat, no l’òptim.
La prioritat següent és millorar avaluació/anotacions i executar un calibratge
esglaonat. No s’han executat nous vídeos, ajustat defaults ni activat recovery
en aquesta revisió.

Reanàlisi reproduïble local: `runs/calibration/study-assessment-v1/analyze_existing.py`,
`assessment.json` i `analysis.log`. Traces, MP4 i resultats originals intactes.

## Fonts primàries de metodologia

- [ByteTrack](https://arxiv.org/abs/2110.06864): associació amb deteccions fortes i febles.
- [BoT-SORT](https://arxiv.org/abs/2206.14651): moviment, aparença i compensació de càmera; el nostre adaptador fixa explícitament la càmera.
- [TrackEval](https://github.com/JonathonLuiten/TrackEval): implementació de mètriques MOT, amb protocols/anotacions corresponents.
