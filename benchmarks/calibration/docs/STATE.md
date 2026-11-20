# Estat de l’estudi

## Detector

YOLOv8m amb **0,001 principal**, **0,002 control**, NMS 0,7, imgsz 1280,
resize 1,5 i max_det 300. Són paràmetres experimentals del banc; no s’han
substituït els defaults de l’aplicació.

La prova ampliada va completar 36 passades sobre 18 vídeos. Amb les referències
d’IA originals, 0,001 tenia caixa compatible en 1.204/1.267 instants visibles;
0,002, en 1.185/1.267. Hi havia 173 exclusions. Són xifres històriques sobre
mostres, abans de les correccions humanes; no una mesura de tot el vídeo.

[Revisió del resultat ampliat](../../../runs/calibration/expanded-localization-v1/assessment/ASSESSMENT.md).

## Referències i revisió humana

La revisió està en curs a [localhost:8766](http://localhost:8766/).
El seu fitxer de treball és
`runs/calibration/expanded-localization-v1/human-review/review-state.json`.
No es mou amb el codi i la seva revisió pot continuar augmentant.

La primera lectura parcial, fixada a la revisió 212, va trobar deteccions útils
en diversos instants que abans quedaven exclosos i caixes suficients que l’IoU
no acceptava. També hi ha fragments útils i solapaments amb assistents.
[Interpretació parcial](../../../runs/calibration/expanded-localization-v1/human-assessment-r212/INTERPRETATION.md).

[Ús de la revisió humana i revaloració](HUMAN_REVIEW.md).

## Proves existents

| Pla a `config/iterations/` | Abast | Estat |
| --- | --- | --- |
| `01-threshold-robustness.json` | 3 vídeos, 4 confiances, 4 trackers | Executat; estudi inicial de llindars. |
| `02-low-detector-thresholds.json` | 3 vídeos, 4 confiances baixes, sense trackers | Executat. |
| `03-localization-candidates.json` | 3 vídeos, 0,001/0,002 | Pla auxiliar conservat. |
| `04-expanded-localization.json` | 18 vídeos, 0,001/0,002 | Executat; revisió humana en curs. |
| `archive/01-detector-confidence.json` | Proposta inicial 0,02/0,05 | Esborrany substituït pel pla robust. |

Les matrius de detectors/trackers són a `config/experiments/`; els plans fixen
quins casos i variants s’executen i quants treballs s’esperen.

## Següent fase: identitat estable

La prioritat passa a associar les deteccions al llarg del vídeo i mantenir
una identitat coherent del gimnasta. **L’ID correspon a la persona; la caixa
és una regió de suport variable, no una delimitació anatòmica precisa.**

S’accepta una caixa una mica més gran, amb marge o incloent temporalment un
assistent, quan ajuda a mantenir el gimnasta localitzat amb el mateix ID.
Un canvi de mida de la caixa no implica un canvi d’identitat. Transferir
l’ID a l’assistent continua sent un error, encara que les caixes se solapin.
Tampoc es considera útil qualsevol caixa que contingui tota l’escena:
l’excés d’àrea i la barreja d’actors s’han de registrar com a costos secundaris.

El recorregut previst és:

1. `perception`: obtenir les deteccions de persona; el detector YOLO executable
   actual continua al banc experimental.
2. `preparation`: preparar representants, alternatives i avisos per a les caixes
   redundants/parcials del mateix fotograma, preservant les deteccions originals.
3. `tracking`: associar candidats entre fotogrames i mantenir els IDs de persona.
   L’avaluació comprovarà específicament que el del gimnasta no es transfereixi.
   La selecció automàtica del gimnasta (`subjects`) continua pendent.
4. Reconstruir esquelets i associar-los a les caixes/IDs; després revisar la
   coherència temporal i geomètrica de les articulacions. Les trajectòries
   articulars són l’objectiu final, no els centres de les caixes. Si s’utilitzen
   retalls o canvis d’escala, conservar les transformacions per expressar les
   articulacions en coordenades del fotograma original.

L’estudi haurà de distingir:

- Caixa principal suficient i candidates parcials/solapades del mateix actor.
- Identitats d’assistents i altres persones presents.
- Observació real, pèrdua i predicció temporal del tracker.

Per valorar la preparació, cal mesurar quina fracció de la caixa corporal de
referència queda coberta per la candidata, juntament amb l’excés d’àrea i la
possible barreja d’actors. És una aproximació geomètrica, no una comprovació
de totes les articulacions. L’IoU i la conservació exacta del candidat humà
continuen sent diagnòstics, però substituir-lo per una caixa més gran que
cobreix el gimnasta no és, per si sol, una pèrdua. Els límits acceptables i la
regla de decisió encara s’han de fixar. La comanda `prepare-boxes` ja exporta
cobertura de referència i proporció d’àrea; els controls 90% i àrea 4× són
diagnòstics exploratoris, no llindars validats.

La continuïtat s’haurà de valorar en finestres de vídeo, amb pèrdues, canvis
d’ID i identitats duplicades, separant observacions i prediccions. Les mostres
disperses actuals no acrediten estabilitat temporal. Les referències d’IA
acceptades per a l’estudi conserven la seva procedència; no es converteixen
en anotacions humanes exhaustives.

La [simulació geomètrica exploratòria](../../../runs/calibration/box-preparation-feasibility-v1/ASSESSMENT.md)
i la seva [galeria](../../../runs/calibration/box-preparation-feasibility-v1/review.html)
mostren riscos de la supressió per IoU/contenció. La seva comparació de
cobertura amb IoU≥0,5 i conservació exacta del candidat és històrica; no és
la funció de decisió de l’objectiu de caixes flexibles acabat de fixar.

La [primera preparació de caixes](../../../src/trampoline_vision/preparation/README.md)
ja és executable: agrupament conservador, salvaguarda de cobertura del
representant, originals intactes i relacions de contenció ambigües. El perfil
`configs/preparation/box-candidates.json` s’activa expressament; els pipelines
de tracking existents continuen amb preparació de caixes desactivada.
El calibratge de la política i la seva avaluació temporal queden pendents.
Els resultats congelats i els llindars del detector no es modifiquen.

La primera execució de la implementació final sobre les 1.440 mostres és
[`box-preparation-v3`](../../../runs/calibration/box-preparation-v3/INTERPRETATION.md):
1.090 alternatives agrupades de 233.299 deteccions, amb totes les fonts
conservades i les 56 caixes útils humanes encara representatives. La reducció
és del 0,47%; no acredita encara una millora de tracking. El temps de preparació
mesurat és de 14,35 s, uns 10 ms per mostra en CPU, sense generació de vídeo.

El [control sobre les caixes validades humanament](../../../runs/calibration/human-approved-redundancy-v1/ASSESSMENT.md)
acota aquesta millora: en 47/56 instants útils continuen altres candidats
solapats o petites caixes contingudes; el recompte local només baixa de 138
a 137 i cap candidat seleccionat agrupa altres fonts. La inspecció visual
mostra parts redundants i també altres persones: les relacions geomètriques
no són duplicats semàntics verificats. La preparació actual conserva la
procedència, però encara no redueix de manera útil aquestes hipòtesis del
gimnasta. Aquest control no modifica la política ni el tracking.

## Comparació de variants de preparació

L’[estudi consolidat](BOX_PREPARATION_STUDIES.md) documenta les variants i
les seves limitacions abans de connectar-les al tracking. Sobre el conjunt
local fix de 193 candidatures, la contenció amb salvaguardes en deixa 95;
l’híbrid anterior d’àncora/densitat i residuals, 82; el model de fortes
protegides i regions febles segur, 89. Tots tres ofereixen cobertura≥95%
dels 56 rectangles humans, però amb costos d’àrea i tractament d’actors diferents.

El model regional segur preserva les 1.054 cobertures IA≥90% anteriors i
n’afegeix 25 geomètricament; la disponibilitat amb àrea≤4× baixa de 887 a 817.
Això encara no demostra detecció corporal millor ni identitats més estables.
Les versions estrictes redueixen més, amb pèrdues de cobertura activa.

El perfil representatiu de 12 caixes està disponible com a opció a
[preparation](../../../src/trampoline_vision/preparation/README.md).
Al replay continu de 12 clips, en les 21 seleccions humanes coincidents
conserva cobertura ≥95% en totes. Entre les 419 referències IA hi ha un
cas clar revisat sense caixa útil, ja absent a YOLO, i tres fragments.
La geometria regional i l’associació continuen sent punts de millora.
[Resultats i evidència per reprendre l’estudi](BOX_PREPARATION_STUDIES.md).
