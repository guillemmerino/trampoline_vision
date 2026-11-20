# Detecció del gimnasta i preparació de caixes

Aquest document explica el camí experimental fins a YOLOv8m a confiança
0,001 i una llista de fins a dotze caixes representatives. L’objectiu
d’aquesta fase és que almenys una candidata localitzi el gimnasta.
S’accepten fragments identificables i marge al voltant del cos. Una caixa
que només toca el gimnasta de passada requereix revisió.

L’estudi ha anat canviant la pregunta i el criteri d’avaluació. Cada
resultat manté el seu denominador, les referències i la mètrica originals.
Les observacions visuals de l’agent i les aprovacions humanes es declaren
amb procedència separada. La conclusió és una configuració de treball
fonamentada en les proves disponibles.

[Taules detallades de preparació](BOX_PREPARATION_STUDIES.md) ·
[Índex de dades i imatges amb hashes](../evidence/box-preparation-v1/index.json).

## 1. Detectors proposats i execucions que els acrediten

La matriu inicial va proposar YOLOv8n i YOLOv8m amb confiances 0,02/0,05,
i controls YOLOv8m de NMS 0,5 i de màxim de vint caixes per àrea.
La configuració del banc descriu una proposta, i els checkpoints
identifiquen quines combinacions es van arribar a executar.

| Execució | Vídeos | Model | Confiances mínimes | Passades de detector |
| --- | ---: | --- | --- | ---: |
| server-rtx5070-v1 | 3 | YOLOv8m | 0,05 | 3 |
| threshold-robustness-v1 | 3 | YOLOv8m | 0,01 / 0,02 / 0,05 / 0,10 | 12 |
| low-detector-thresholds-v1 | 3 | YOLOv8m | 0,01 / 0,005 / 0,002 / 0,001 | 12 |
| expanded-localization-v1 | 18 | YOLOv8m | 0,001 / 0,002 | 36 |

Les metadades de les 63 passades registren pesos i vídeo per SHA-256,
precisió, recompte de fotogrames i configuració efectiva. YOLOv8n,
la inferència amb NMS 0,5 i el control de màxim vint per àrea queden
com a propostes sense execució acreditada en aquest conjunt de runs.
Les comparacions posteriors de NMS es van fer sobre caixes ja desades.

Per tant, aquests resultats fonamenten l’ajust de YOLOv8m. La comparació
experimental entre arquitectures queda oberta. Els estudis més antics
basats en CSV amb paràmetres originals incomplets tenen abast propi i
s’han de consultar abans d’atribuir-los una configuració exacta.

[Inventari contrastat amb checkpoints](../evidence/box-preparation-v1/detector-execution-inventory.json) ·
[Matriu inicial](../config/experiments/baseline.json).

## 2. Per què es va baixar la confiança

La primera execució amb confiança 0,05 tenia caixa compatible en 48 de
61 fotogrames visibles anotats. Es va plantejar baixar el llindar per
retenir propostes febles en girs, inversions i imatges desdibuixades.
Durant les comparacions es van fixar model, NMS 0,7, mida d’entrada
1280, resize 1,5, precisió FP32 i màxim 300 deteccions.

| Confiança | IoU≥0,50 /61 | Caixes de tots els actors als tres clips |
| --- | ---: | ---: |
| 0,10 | 48 | 65.586 |
| 0,05 | 48 | 106.136 |
| 0,02 | 54 | 176.668 |
| 0,01 | 56 | 219.372 |
| 0,005 | 57 | 257.737 |
| 0,002 | 59 | 328.974 |
| 0,001 | 59 | 406.609 |

Baixar de 0,01 a 0,002 aporta tres mostres compatibles. Entre 0,002 i
0,001 el recompte empata, però a AGE3 001351 #102 l’IoU puja de 0,513
a 0,751. A #180 persisteix un fragment. Al pilot, el màxim observat de
caixes per fotograma és 227, per sota de 300.

L’ampliació a 18 vídeos confirma un avantatge de 0,001 respecte de
0,002 en 19 mostres, amb 1.204/1.267 davant de 1.185/1.267 i cap pèrdua
aparellada. Sobre les àncores uniformes visibles, el resultat és
721/760 davant de 709/760. El volum total puja un 23,09%. Això justifica
0,001 com a principal quan la prioritat és conservar deteccions febles,
amb 0,002 com a control de volum.

NMS, escala i màxim de deteccions van ser constants d’aquella prova.
La sensibilitat a aquests valors necessita una comparació específica.
El límit 300 tampoc se satura en l’ampliació, on el màxim és 232.
La reserva temporal ja es va consultar i les referències són d’IA
provisionals acceptades per a l’estudi.

[Resultats originals de llindars](../evidence/box-preparation-v1/low-thresholds-analysis.json.gz) ·
[Resultats per vídeo als 18 clips](../evidence/box-preparation-v1/expanded-localization-per-video.csv).

## 3. Quin problema produeix el volum de caixes

Les imatges mostren situacions diferents que requereixen decisions
diferents. El públic i els jutges poden ser persones ben detectades que
ocupen places de la llista. Altres propostes corresponen a soroll sobre
elements de l’escena. Sobre el gimnasta hi ha caixes del cos, tors, cap i
contorns alternatius de la mateixa persona. Finalment, hi ha contenidors
amplis que barregen gimnasta, assistent i fons.

A 0,001 hi ha 685 mostres anotades amb almenys dues caixes compatibles.
És un recompte de multiplicitat geomètrica. Per saber si cadascuna és
una part redundant, una altra persona o una proposta incorrecta cal
revisar-la visualment. La mostra dirigida r214 identifica 56 caixes
útils de cinc vídeos AGE1, amb 54 suficients i dues parcials.

El NMS inicial explica part de la redundància. Una caixa de mig cos
dins d’una caixa de cos sencer pot tenir IoU 0,5. Amb NMS 0,7, totes
dues poden sobreviure. La contenció relativa, IoS, detecta millor
aquesta relació, però també és alta entre persones superposades.

A AGE1 000905 #720 hi ha set alternatives petites condicionades dins
la candidata seleccionada. A 002139 #679, una caixa confiada conté la
seleccionada i també l’assistent. El segon cas explica el risc
d’escollir sempre la caixa més gran.

[Exemple favorable d’agrupament i casos problemàtics](../evidence/box-preparation-v1/images/shortlist-regions.jpg) ·
[Contenidor amb assistent, #679](../evidence/box-preparation-v1/images/containment-assistant-679.jpg) ·
[Recomptes de multiplicitat](../evidence/box-preparation-v1/feasibility.json).

## 4. Què es va provar per eliminar redundància

Les primeres simulacions reaplicaven supressió a les 233.299 deteccions
dels 1.440 fotogrames desats. Aquesta operació parteix de caixes que
ja havien passat pel NMS 0,7 del detector.

| Proposta | Caixes restants | Mostres compatibles /1.267 | Caixes humanes exactes /56 |
| --- | ---: | ---: | ---: |
| Entrada original | 233.299 | 1.204 | 56 |
| NMS addicional 0,50 | 153.269 | 1.168 | 44 |
| NMS addicional 0,60 | 178.566 | 1.187 | 51 |
| NMS addicional 0,65 | 198.509 | 1.195 | 52 |
| IoS≥0,90, supressió general | 125.214 | 1.034 | 41 |
| Contenció condicionada | 195.759 | 1.197 | 54 |

NMS 0,50 redueix el volum però perd 36 mostres compatibles anteriors.
La supressió general per IoS en perd 170. La contenció condicionada
hi afegeix IoS≥0,95, proporció d’àrea entre 0,10 i 0,70 i confiança
petita≤0,25× confiança gran. Tot i les salvaguardes, perd set mostres.

L’agrupament conservador final S0 reté les 56 seleccionades i agrupa
1.090 alternatives, un 0,47% del total. Però al voltant de les
seleccions humanes, les alternatives només passen de 138 a 137.
Es conserva com a base de comparació i de procedència. La insuficient
reducció observada va motivar explorar grups de parts més diferents.

La decisió va ser abandonar la supressió general com a solució principal
i conservar els contraexemples. La contenció continuava sent una
operació a estudiar amb salvaguardes. Soft-NMS i Weighted Boxes Fusion
es van discutir, amb resultat experimental pendent.

[Estadístiques dels controls](../evidence/box-preparation-v1/feasibility.json) ·
[Auditoria del poc efecte local de S0](../evidence/box-preparation-v1/human-redundancy.json) ·
[Política final S0](../evidence/box-preparation-v1/conservative.json).

## 5. Per què s’hi van afegir àncores i suport de densitat

La confiança aporta una pista per triar un representant. Entre 98
petites contingudes analitzades, 76 tenen menys confiança que la
seleccionada i 22 en tenen més. Dels deu casos seleccionats amb score
inferior a 0,01, vuit tenen alguna petita interior més confiada.
La inspecció mostra tant interiors corporals més ajustades com
caixes parcials de cap i tors que necessiten més extensió.

Es van provar contenidors observats amb cobertura directa de cada
font, proporcions d’àrea, límit del 10% d’imatge i confiança relativa.
A continuació, àncores fortes amb expansió recolzada en veïnes i una
fase residual. Finalment, un model que protegeix fortes aïllades i
genera regions provisionals quan un veïnat feble té suport suficient.

| Família de referència | Globals | Grups locals /193 | Rectangles humans coberts≥95% |
| --- | ---: | ---: | ---: |
| S0 | 232.209 | 193 | 56 |
| Contenció amb salvaguardes | 161.232 | 95 | 56 |
| Híbrid de densitat i residuals | 157.300 | 82 | 56 |
| Fortes protegides i regional segur | 164.772 | 89 | 56 |

En contenció, la confiança relativa evita alguns contenidors febles
enormes. El màxim 3,75× de la regió respecte de la caixa humana és un
resultat observat. El límit configurat era 10× respecte de cada font
i 10% del fotograma. En la família regional, retornar a candidates
actives el suport no explicat conserva cobertura, amb més regions i
més àrea.

La densitat compta propostes solapades del mateix detector, que estan
correlacionades. També pot agrupar fons. A #889, una regió feble
recupera l’extensió que una àncora parcial deixava fora. A #645,
la regió continua incloent jutges. Això justifica suport feble
controlat, amb plausibilitat corporal encara pendent d’avaluar.

[Confiances contrastades](../evidence/box-preparation-v1/confidence.json) ·
[Variants de contenció](../evidence/box-preparation-v1/containment.json) ·
[Variants d’àncores i densitat](../evidence/box-preparation-v1/density.json) ·
[Variants regionals](../evidence/box-preparation-v1/regional.json) ·
[Àncora parcial #889](../evidence/box-preparation-v1/images/density-partial-889.jpg).

## 6. Per què es van afegir zona, silueta, rànquing i tall

L’agrupament espacial encara conserva moltes persones reals del públic.
La contenció deixa 112 caixes de mitjana i la fase regional, 114,4.
Una zona ampla del trampolí, marcada mirant el panell de càmera,
redueix aquesta última entrada a 87,5. Per arribar a dotze, cal ordenar
i limitar les hipòtesis actives.

Escollir només per confiança afavoreix altres persones ben visibles.
La màscara de silueta aproxima què canvia respecte del fons fix,
calculat amb 21 fotogrames del clip. El rànquing inicial prioritzava
alguns fragments petits amb molta proporció de primer pla. Donar més
pes a l’extensió del component va recuperar caixes corporals. Aquest
canvi i la salvaguarda de cobertura es van ajustar sobre les mateixes
dades, amb validació independent pendent.

| Proposta espacial | Places | IA amb cobertura≥90% /1.267 | Caixa humana coberta≥95% /56 |
| --- | ---: | ---: | ---: |
| Confiança sola | 5 | 250 | 27 |
| Primer pla inicial | 5 | 724 | 51 |
| Primer pla inicial | 8 | 894 | 56 |
| Més pes d’extensió | 8 | 1.061 | 56 |
| Extensió i contenció protegida | 8 | 1.065 | 56 |
| Extensió i contenció protegida | 12 | 1.078 | 56 |
| Mateixa ordenació, sense fusió final | 12 | 1.078 | 56 |

La contenció final demana cobertura≥95% de la caixa absorbida i
IoU≥0,67 o compatibilitat de fragment del mateix component. A dotze,
la cobertura empata amb el control sense fusió. Entre les tres
primeres places s’obtenen 798 cobertures IA davant de 775. L’avantatge
demostrat d’aquesta operació és modest i depèn del criteri. El tall a
dotze conserva 1.053 de les 1.054 cobertures anteriors S0 i afegeix
25 guanys geomètrics. El control d’àrea≤4× baixa de 887 a 817.

La zona i la silueta introdueixen supòsits d’escenari. La zona és
manual i el fons és retrospectiu amb càmera fixa. El públic en
moviment i la lona també creen components. Amb zona flexible, una
caixa exterior pot competir pel rànquing. Amb zona obligatòria, cal
el centre dins o almenys el 55% de la caixa dins. Una caiguda fora
d’aquest rectangle necessita una mostra específica per validar-la.

[Les 23 variants i els seus resultats](../evidence/box-preparation-v1/shortlist-spatial-summary.json) ·
[Fons i components](../evidence/box-preparation-v1/images/foreground-comparison.jpg) ·
[Casos recuperats pel pes d’extensió](../evidence/box-preparation-v1/images/shortlist-recoveries.jpg).

## 7. Criteri d’èxit i decisió provisional

La lectura de cada taula requereix conservar-ne el criteri.

| Criteri | Què comprova | Límit d’interpretació |
| --- | --- | --- |
| IoU | Encaix entre les dues caixes, penalitzant marge | Una caixa parcial útil pot quedar sota el llindar |
| Cobertura de referència | Fracció del rectangle anotat dins una candidata | Un contenidor molt gran pot superar el control |
| Cobertura amb límit d’àrea | Cobertura i excés de regió alhora | El límit acceptat continua sent exploratori |
| Caixa humana exacta | Conservació de la candidata triada | Una altra candidata també pot ser adequada |
| Localització visual útil | La caixa permet situar el gimnasta o un fragment identificable | Cal judici explícit, amb procedència i exemple |

El criteri adoptat per continuar és disposar d’una caixa útil entre
les dotze. Una caixa amb marge o parcialitat pot ser acceptable.
El recompte total es valora junt amb l’extensió del cos i la barreja
d’altres persones.

La comprovació posterior sobre 419 fotogrames amb referència visible
va revisar amb més detall els casos de pitjor geometria. En 393 hi
havia una caixa que cobria≥25% de la referència i tenia≥50% de la seva
pròpia àrea dins la referència. Entre els 26 restants, la lectura
visual de l’agent identifica 22 casos coberts per regions àmplies,
tres fragments identificables i un cas clar sense caixa útil, AGE3
001351 #97. En aquest últim, el millor solapament cobria només el 9%
ja entre les deteccions originals YOLO. Aquesta inspecció dels
casos dubtosos complementa el diagnòstic geomètric. Els altres
fotogrames dels clips continuen sense validació visual exhaustiva.

En les 21 seleccions humanes prèvies coincidents amb aquells clips,
es conserva≥95% de cobertura en totes. Aquesta mostra és diferent
de les 56 seleccions del calibratge espacial i dels 419 rectangles
IA. Els denominadors es mantindran sempre identificats.

[Absència clara #97](../evidence/box-preparation-v1/images/entry-97.jpg) ·
[Fragment #180](../evidence/box-preparation-v1/images/entry-180.jpg) ·
[Fragment #510](../evidence/box-preparation-v1/images/entry-510.jpg) ·
[Caixes i ordre dels exemples](../evidence/box-preparation-v1/shortlist-entry-cases.json).

La configuració seleccionada és YOLOv8m a 0,001, amb 0,002 de control,
i preparació regional, rànquing per silueta i contenció protegida amb
dotze places. Els estudis futurs poden comprovar arquitectures
alternatives, escala i NMS d’inferència, fons adaptable, altres plans
de càmera i geometria més compacta. Els llindars interns i els pesos
de rànquing són hipòtesis explorades en aquesta captura.

Per reprendre l’estudi, cal començar pels comparadors i els casos
adversos guardats. Repetir-los té sentit com a regressió quan es canviï
la implementació. Una nova hipòtesi ha d’indicar quina fallada concreta
pretén corregir i contrastar el guany amb les pèrdues en els mateixos
fotogrames abans d’ampliar-ne l’abast.

## Integració actual: zona comuna centrada i auditoria

El pipeline `configs/pipelines/track-boxes.json` activa ara explícitament
`configs/preparation/representative-boxes.json` i el manifest calibrat amb
YOLOv8m a 0,001; ja no consumeix el CSV legacy. El perfil manté S0, regions,
contenció, silueta i tall de 12, però configura una zona comuna
`[0.06, 0.25, 0.94, 0.93]` amb mode `soft`. S’assumeix el trampolí centrat,
amb marges laterals simètrics; no es consulta el panell de càmera de cada cas.
Les caixes exteriors competeixen pel mateix pressupost, amb la preferència
espacial del rànquing. No s’eliminen directament per estar fora de zona.

**Aquesta és una variant nova de configuració.** Les mesures anteriors,
amb zones per clip, es conserven com a evidència històrica; no demostren el
rendiment de la zona centrada. Els marges no s’han calibrat com a òptims.
Cal contrastar la variant amb els mateixos fotogrames i casos laterals abans
d’atribuir-li les cobertures històriques. El fons continua sent fix per vídeo.

`prepare_with_audit` i `preparation_record(..., audit=...)` permeten recuperar
recomptes per fase, puntuacions i motius de selecció, fusió i exclusió, amb
els originals íntegres. `review-boxes` en genera una mostra visual independent.
El prototip `benchmarks/calibration/engine/representative.py` queda identificat
com a comparador històric; les evolucions s’implementen a `src/preparation`.

### Comprovació de funcionament de la integració

La galeria local `runs/calibration/centered-soft-review-v1/index.html` mostra
12 fotogrames uniformes de `JPN_AGE_1_000905_31.0`, processats pel codi de
producció amb el perfil centrat soft. Es reutilitza el CSV sense inferència:
114–143 originals per fotograma, 12 candidates finals en cadascun, 19,6 ms
mitjans de preparació (inclou l’auditoria) i 2,81 s totals amb lectura del vídeo,
fons, JSONL i JPG, sense MP4. És una mesura puntual en aquest servidor,
no un pressupost garantit ni una comparació exhaustiva de precisió.
S’ha comprovat el SHA-256 del vídeo contra `detector.json` i que les decisions
particionen exactament els originals sense pèrdues ni duplicacions de procedència.
`summary.json` i `frames.jsonl` guarden les dades de la comprovació.

Validació automatitzada: 169 tests del projecte i 70 del banc. Inclou
exclusions, absorció després d’omplir el pressupost, serialització de
l’auditoria i elegibilitat de caixes exteriors quan s’omet el mode (soft). No s’han repetit inferències ni estudiat identitats.

### Contrast posterior de la zona comuna

La [comparació de zones](ZONE_COMPARISON.md) ja s’ha executat sobre els 18 clips
i 1.440 fotogrames anotats, reutilitzant deteccions: zona antiga hard/soft
1078/1267 a cobertura IA90; zona comuna soft 1077/1267. Les tres variants
mantenen 56/56 caixes útils validades (cobertura95) i 52/55 referències humanes
(cobertura90). La pèrdua addicional és AGE1 002837 frame1262: la caixa ampla
que era candidata 12 queda fora, però encara entren caixes del gimnasta, amb
menys cobertura dels braços alçats. L’agent ha inspeccionat aquest cas i 12
altres discrepàncies; no ha validat visualment totes les mostres.
La recomanació és mantenir la zona comuna soft, amb aquests límits explícits.
No s’han canviat paràmetres. L’[informe detallat](../../../runs/calibration/zone-comparison-v1/REVIEW.md)
separa mètriques geomètriques, observacions visuals i límits del detector.
