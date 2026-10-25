# 25. Prova de tracking amb deteccions de persona independents

Estudi executat el 24 d'octubre de 2026 sobre el paquet 0.4.0 i `trackers==2.6.1`.
El codi i les dades petites reproduïbles són a
[`study-04`](../benchmarks/cases/JPN_AGE_1_000905_31.0/study-04/README.md).

## Resultat i decisió

Les caixes YOLO enregistrades milloren la cobertura geomètrica del gimnasta
respecte a les caixes derivades d'OpenPose. El canvi de mesures, tot sol,
encara no proporciona una identitat fiable durant tot el vídeo.

S'ha obtingut una mostra local de 2,9 segons amb una mateixa identitat,
observacions exportades i incidències explícites. És una mostra diagnòstica
seleccionada després de l'execució; no demostra selecció automàtica del
gimnasta ni resolució del tracking complet. L'increment 2 continua obert.

La prova avala continuar amb detecció de persona i pose independents.
La utilitat de combinar-les per recuperar identitats encara s'ha de mesurar.

## Què s'ha processat

- Vídeo `JPN_AGE_1_000905_31.0.mp4`: 930 fotogrames, 960 × 1080, 30 FPS, 31 s.
- CSV de `TFM/Tracking_system/output_videos/`, acabat en `_bboxes.csv`:
  18.600 caixes, 20 per fotograma, índexs de vídeo 0–929 i classe persona.
- Confiança original del detector i coordenades en píxels del vídeo original.
- Tots els actors, sense seleccionar la caixa més gran ni aplicar una ROI manual.

El `det_id` del CSV és un índex local del fotograma: no és una identitat.
El lector comprova capçalera, tipus, duplicats, límits de coordenades,
confiança i cobertura explícita de tots els fotogrames d'aquest cas.

L'script històric utilitza Ultralytics i té `yolov8m.pt` com a valor per defecte.
El CSV no registra els pesos exactes ni tota la configuració de l'execució
que el va generar; no podem certificar-los només a partir d'aquest fitxer.
El SHA-256 del CSV queda fixat a `results.json`.

No s'ha executat inferència nova ni s'han entrenat o descarregat pesos.

## Relació amb OpenPose i amb el procés antic de TFM

El procés antic detectava persones, preparava retalls i enviava aquests
retalls a OpenPose. Aquest estudi consumeix directament les caixes desades
com a mesures del tracker. No introdueix els retalls a OpenPose.

Les articulacions no intervenen en les assignacions d'aquesta prova.
El contenidor canònic actual exigeix BODY25; l'adaptador experimental
deixa els 25 punts explícitament absents i marca `pose_not_loaded`.
`BoxMeasurement.source` és `detector` i conserva la confiança YOLO real.
Això permet reutilitzar el registre d'identitats sense inventar poses.
La forma definitiva del contracte independent de detecció de persones
queda per a l'increment d'integració, fora d'aquest prototip.

Una prova híbrida posterior haurà de llegir en paral·lel les poses globals
independents i associar-les a les caixes. Els ZIP antics de poses sobre
retalls tenen un altre sistema de coordenades i no es poden tractar com
a poses globals sense reconstruir i validar les transformacions.

## Protocol i resultats dispersos

S'han executat set variants sobre els 930 fotogrames, començant sempre a
zero. Les tres principals comparteixen confirmació de naixement de tres
observacions fortes consecutives, retenció de pèrdua de 0,5 s i IoU 0,1.
ByteTrack s'ha provat mitjançant el port experimental de l'estudi 03;
no s'ha afegit com a backend de producció.

Les comparacions utilitzen les mateixes 25 caixes visuals aproximades de
l'estudi 03: 13 del gimnasta i 12 de l'assistent posterior. Hi ha assignació
unívoca per fotograma, i una predicció no compta com a observació.
Són anotacions disperses sense revisió humana independent, no mètriques
HOTA/MOTA ni una classificació general de trackers.

Amb IoU ≥ 0,3:

| Mesures / variant | Caixa disponible del gimnasta | Matches observats | IDs als matches | Canvis entre matches |
| --- | --- | --- | --- | --- |
| OpenPose, referència de l'estudi 03 | 8/13 | 7/13 | Veure estudi 03 | Veure estudi 03 |
| YOLO + OC-SORT | 13/13 | 11/13 | 5 | 4 |
| YOLO + ByteTrack, confiança ≥ 0,1 | 13/13 | 12/13 | 9 | 8 |
| YOLO + ByteTrack, febles només per mantenir IDs confirmats | 13/13 | 13/13 | 9 | 8 |

En la tercera variant s'admeten mesures de confiança ≥ 0,02 per mantenir
una identitat confirmada; els naixements continuen exigint tres mesures
consecutives de confiança ≥ 0,1. No s'interpreta 13/13 com a continuïtat:
els nou IDs mostren precisament que continua havent-hi fragmentació.

Amb IoU ≥ 0,5, les caixes YOLO són disponibles en 11/13 instants i els
matches observats són 9/13, 10/13 i 11/13 respectivament. Aquesta sensibilitat
al marge de caixa és un altre motiu per no convertir el pilot en precisió global.

Els quatre controls addicionals d'OC-SORT varien confiança 0,02, IoU 0,02
i pes de direcció 0. Cap control elimina la fragmentació: hi ha entre
sis i set IDs als instants revisats. Les configuracions exactes i els
resultats de tots set controls són a `study-04/results.json`.

Les deteccions desades només cobreixen l'assistent posterior en 2/12
anotacions a IoU 0,3. Per tant, la millora observada en el gimnasta no es
pot extrapolar a totes les persones petites o parcialment ocultes.

## Mostra de trajectòria i fallades comprovades

S'ha revisat visualment cada fotograma de l'interval 400–486 amb làmines
del vídeo original i les caixes observades. La mostra correspon a
13,333–16,233 s, incloent la durada de l'últim fotograma.

L'ID `ocsort:36` manté el gimnasta en aquest tram, incloses posicions
invertides. Els 87 fotogrames es desglossen així:

- 80 amb mesura observada i 7 amb caixa predita.
- Dins de les 80 observacions, 7 tenen extensió ambigua prop de l'assistent
  del primer pla: fotogrames 437–442 i 486.
- Les prediccions són als fotogrames 406, 408, 449, 450, 474, 475 i 481.

El CSV exporta les coordenades originals, el centre de caixa, l'evidència,
el candidat, la seva confiança i l'avís de revisió. No hi ha suavitzat,
unió d'IDs ni farciment d'observacions. El vídeo mostra les caixes predites
discontínues en taronja i les ambigües en groc; la línia només uneix centres
observats consecutius sense ambigüitat marcada. El centre de caixa varia
amb la postura i l'extensió detectada: no és el centre de massa.

Fora de la mostra, **el mateix ID segueix un jutge** als fotogrames 300,
360 i 390, mentre el gimnasta és en un altre lloc. Al fotograma 495 el
gimnasta ja correspon a `ocsort:78`. Conservar el número d'ID no assegura
que es conservi l'actor. Els matches dispersos, tot sols, no detecten
aquestes transferències intermèdies.

## Artefactes locals

Carpeta `runs/tracking-yolo-study-04/`:

- Tres JSONL complets d'assignacions i `summary.json`.
- `diagnosis.json`: comparació amb les caixes visuals disperses.
- `all-actors/overlay.mp4`: vídeo complet amb totes les identitats.
- `all-actors/report.json`: recompte i verificació temporal del vídeo complet.
- `sample/overlay.mp4`: mostra de 2,9 s, ID i interval seleccionats manualment.
- `sample/trajectory.csv`: 87 registres, amb observacions i prediccions distingides.
- `sample/report.json`: configuració de revisió, recomptes i verificació temporal.
- `review/`: làmines de revisió dels 87 fotogrames, comparativa i previsualització.

Els quatre controls addicionals són a `runs/tracking-yolo-study-04-calibration/`.
Els MP4 conserven tots els fotogrames seleccionats i els seus temps de
presentació, comprovats amb ffprobe. Aquesta verificació valida la
recodificació; la continuïtat d'identitat té les limitacions descrites.
Els artefactes grans queden a `runs/`, fora del control de versions.

## Següent increment proposat a partir de l'evidència

1. Fixar una anotació d'identitat més densa als contactes amb assistents,
   als passos davant la fila de jutges i a les inversions. Revisar també
   vídeos diferents per evitar ajustar el sistema només a aquest cas.
2. Fer que la recuperació d'identitat consideri plausibilitat del moviment
   i evidència visual de l'actor, a més del solapament de les caixes.
   La càmera fixa i la zona del llit poden aportar context, però una ROI
   sola no separa persones que se superposen en la projecció de la imatge.
   Aquestes són hipòtesis a comparar, no millores ja demostrades.
3. Introduir les poses independents com una altra font d'evidència, amb
   correspondències unívoques i sortida explícitament ambigua quan no es
   pugui decidir. Mesurar per separat identitat i qualitat articular.

No es canvien els defaults de producció a partir d'aquest únic vídeo.
La prioritat continua sent una trajectòria d'actor validada abans de
construir la segmentació i la puntuació sobre les seves articulacions.
