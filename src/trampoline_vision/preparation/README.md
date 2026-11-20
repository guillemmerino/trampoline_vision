# Preparació de deteccions per al tracking

Aquest paquet transforma un `FrameDetections` en un `TrackingFrame` d’un sol
instant. El camí conservador usa només caixes i el perfil representatiu usa
també els píxels del fotograma i el fons fix del clip. El tracking continua
assignant els IDs després de la preparació.

L’objectiu és mantenir la cobertura del gimnasta amb caixes de suport flexibles.
Una caixa més ampla pot ser útil, però tenir més àrea no garanteix cobrir les
cames o el cap: per agrupar, el representant ha de cobrir una fracció explícita
de cadascuna de les caixes originals.

## Fitxers i objectes

| Fitxer / objecte | Responsabilitat |
| --- | --- |
| `pipeline.py`: `prepare_frame`, `prepare_frames` | Entrada pública i stream mandrós. Separa fonts de caixa i de pose; rebutja barrejar-les implícitament. |
| `config.py`: `BoxPreparationPolicy` | Regles de caixa, immutables i validades; desactivades per defecte. |
| `config.py`: `PreparationConfig` | Configuració efectiva completa. `box` i `deduplication` continuen corresponent a poses; `box_preparation` a caixes. |
| `boxes.py`: `prepare_boxes` | Construeix candidats, avisos i relacions, i comprova que totes les fonts apareguin exactament una vegada. |
| `boxes.py`: `group_boxes` | Agrupa alternatives febles de geometria semblant, compatibles amb tots els membres. |
| `boxes.py`: `select_representative` | Tria la caixa observada de més àrea del grup; desempata per confiança i ID. |
| `boxes.py`: `find_box_relations` | Proposa contencions ambigües entre representants, sense fusionar actors. |
| `pose.py`, `deduplication.py` | Camí existent de preparació de poses; no s’utilitzen per deduplicar YOLO. |
| [`BoxRelation`](../contracts/tracking.py) | Relació local amb extrems, IoU, IoS, proporció d’àrea i tipus `ambiguous_containment`. |
| [`preparation_record`](../results/preparation.py) | Exporta font completa, candidats, relacions i configuració, independentment del tracking. |

## Què es conserva al perfil conservador

`TrackingFrame.source` és la mateixa instància d’entrada. Les deteccions
`PersonBoxDetection` conserven ID, geometria, score, classe i `DetectionProvenance`.
Cada `TrackingCandidate.source_detection_ids` referencia les fonts del grup:
la primera és la que aporta `measurement`, les altres són alternatives
recuperables a `source`. La mesura conserva la caixa i el score originals;
no es fan mitjanes, unions, padding ni sumes de confiança.

Les relacions referencien candidats, no tornen a consumir les fonts. Una caixa
pot tenir diversos contenidors possibles. `possible_partial` significa sospita
geomètrica: no afirma que sigui un cap, un tors ni la mateixa persona que el
contenidor. Els IDs de detecció i de candidat són locals al fotograma.

La garantia comença a les deteccions rebudes: no recupera propostes eliminades
prèviament pel NMS de YOLO. L’exportació completa és `preparation_record`; el
JSONL de tracking existent continua sent compacte i no exporta totes les
geometries originals agrupades ni aquestes relacions. Cal conservar l’auditoria
de preparació quan s’utilitzin agrupaments.

## Política experimental de caixes

El perfil explícit és [`box-candidates.json`](../../../configs/preparation/box-candidates.json).
Cap pipeline de tracking existent s’ha canviat per activar-lo automàticament.

| Camp | Valor del perfil | Significat |
| --- | ---: | --- |
| `enabled` | true | Activa agrupament i relacions. El default Python és false. |
| `min_duplicate_iou` | 0,65 | Agrupar requereix IoU estrictament superior. |
| `min_size_similarity` | 0,80 | Mínim menor/major d’amplada i d’alçada. L’àrea es controla indirectament amb IoU. |
| `max_center_distance_ratio` | 0,15 | Separació màxima de centres per eix / menor dimensió. |
| `max_alternative_score_ratio` | 0,25 | Confiança de l’alternativa / ancoratge més confiat. |
| `min_representative_coverage` | 0,95 | Intersecció amb el representant / àrea de cada membre, abans d’acceptar el grup. |
| `min_containment_ios` | 0,95 | Intersecció / menor àrea per proposar una contenció. |
| `min_contained_area_ratio` | 0,10 | Límit inferior d’àrea petita / gran. |
| `max_contained_area_ratio` | 0,70 | Límit superior d’àrea petita / gran. |

Són hipòtesis conservadores, no defaults òptims demostrats. La referència del
gimnasta i els veredictes humans no intervenen en aquestes funcions. El grup
s’ancora per confiança; si el representant de més àrea no cobreix prou tots
els membres, l’alternativa es manté separada. La nova mida no es fabrica.
El score del representant pot baixar: queda marcat amb
`representative_has_lower_confidence`. Un consumidor ha de distingir aquest
fet de la confiança de les altres fonts, que continua disponible.

## Ús conservador des de Python

```python
from trampoline_vision.preparation.config import BoxPreparationPolicy, PreparationConfig
from trampoline_vision.preparation.pipeline import prepare_frame
from trampoline_vision.results.preparation import preparation_record

config = PreparationConfig(box_preparation=BoxPreparationPolicy(enabled=True))
prepared = prepare_frame(source, config)  # source: FrameDetections del lector.
record = preparation_record(prepared, config)
```

## Execució independent i revisió

Des de l’arrel del repositori, sense models, GPU ni tracking:

```bash
PYTHONPATH=src python3 -m benchmarks.calibration prepare-boxes \
  --bundle runs/calibration/expanded-localization-v1/human-review/bundle.json \
  --config configs/preparation/box-candidates.json \
  --decisions runs/calibration/expanded-localization-v1/human-review/review-state.json \
  --output runs/calibration/box-preparation-review-v1
```

L’output ha de ser nou. `frames.jsonl` conté les dades completes; `result.json`
els diagnòstics per mostra i recursos; `ASSESSMENT.md` el resum; `inputs.json`,
`config.json`, la instantània de decisions i `checksums.json` permeten una
revisió independent. Només una execució amb resultat i checksums és completa.
El paquet d’entrada de revisió només conté fotogrames mostrejats, no tot el vídeo.

El temps de preparació exclou adaptació, lectura, diagnòstic i exportació. El
total els inclou, sense generació de vídeo. El RSS del procés inclou carregar
tot el bundle; no és el consum incremental del preparador. Es reutilitzen les
deteccions desades, sense cache de models o descriptors.

La cobertura diagnòstica és intersecció amb la referència / àrea de referència,
amb excés d’àrea separat. Els controls 90% i 4× són punts de lectura, no una
funció d’acceptació calibrada. Les anotacions d’IA mantenen la seva procedència
i limitacions; la cobertura de caixes humanes seleccionades tampoc acredita
articulacions completes. La qualitat dels IDs requereix una fase posterior.

## Perfil representatiu de 12 caixes

El [perfil representatiu](../../../configs/preparation/representative-boxes.json)
activa S0, agrupament regional, evidència de primer pla, contenció protegida i
un màxim de 12 candidates. El perfil compartit usa `zone_mode: "soft"` i
`zone: [0.06, 0.25, 0.94, 0.93]`, en coordenades xyxy normalitzades de **tot**
el fotograma. S’assumeix un trampolí centrat: marge lateral del 6% a cada
costat, límit superior al 25% i inferior al 93%. És una preferència de
rànquing, sense retallar els píxels ni excloure directament salts alts,
caigudes laterals o caixes fora de zona. El tall de 12 sí que pot excloure
candidates. No hi ha detecció automàtica del trampolí ni adaptació per clip.

Aquests marges són una hipòtesi comuna de configuració, no un òptim calibrat.
Les proves històriques usaven zones segons el panell de càmera; els seus
resultats no validen automàticament aquesta variant centrada. Una
[comparació aparellada posterior](../../../benchmarks/calibration/archive/detection-preparation-v1/docs/ZONE_COMPARISON.md)
en 18 clips conserva 56/56 caixes útils validades i introdueix un únic canvi
negatiu al diagnòstic IA90 (1078 → 1077/1267), amb el gimnasta encara localitzat
en la inspecció d’aquell cas. És evidència de treball, no detecció universal. El fons medià
sí que s’estima per vídeo a partir dels píxels, sense anotacions ni zona manual.

`configs/pipelines/track-boxes.json` activa explícitament aquest perfil i
consumeix el nou manifest `calibrated-boxes.example.json`, amb les deteccions
verificades de YOLOv8m a 0,001. El manifest antic `.boxes.example.json` es
conserva per reproduir el CSV legacy. Sense `preparation_config`, el motor
continua produint una candidata per detecció; no hi ha cap perfil global ocult.

### Zona obligatòria a la configuració

Quan el perfil representative_boxes està actiu, zone és un camp requerit.
Si falta, la càrrega del JSON dona l’error representative_boxes.zone is
required. També es rebutgen valors null, rectangles d’àrea zero i
coordenades fora de l’interval [0, 1]. La zona es declara en tots dos modes. Si s’omet `zone_mode`, s’usa `soft`.
Amb hard filtra les caixes abans d’ordenar-les. Amb soft les caixes de fora
poden competir i la zona aporta una preferència en la puntuació.

Per declarar tot el fotograma com a zona, es pot usar [0, 0, 1, 1].
En aquest cas les caixes observades dins la imatge passen el filtre de
zona i el rànquing conserva la preferència horitzontal pel centre.

L’entrada són deteccions de persona i imatges BGR uint8 originals amb la
mateixa geometria. Al pipeline de vídeo el fons és una mediana de fins a
21 fotogrames previs al límit final de l’interval de processament. Per a
vídeo complet s’espaiaran de principi a final. És una operació
retrospectiva amb càmera fixa. Després es calcula la màscara per cada
fotograma i tot el model de caixes treballa dins d’aquell instant.

S0 conserva la mateixa política de similitud i membres. El perfil
representatiu omet només l’exportació de relacions S0 perquè la fase
regional calcula el seu propi veïnat. Un ancoratge és fort a partir de
0,1. Pot absorbir suport feble i créixer fins a 1,5× si té score≥0,5 o
3× per als altres forts, amb suport addicional i el límit d’imatge.
Les febles residuals necessiten almenys quatre candidates compatibles
per construir una extensió. Les ambigües retornen al conjunt feble.

El rànquing combina l’àrea relativa ocupada pel component canviat,
quant component abasta la candidata, nombre de píxels de primer pla,
score original i posició. És el valor que decideix l’ordre, independent
del score que rep el tracker. En la contenció final la candidata de
més prioritat ha de cobrir ≥95% de l’altra, i passar la semblança
IoU≥0,67 o el test de fragment amb component comú. La geometria de la
guanyadora es conserva. Les hipòtesis de fora del tall romanen
accessibles des de la font original.

### Responsabilitat de les peces

| Fitxer i element | Responsabilitat |
| --- | --- |
| [config.py](config.py), RepresentativeBoxPolicy | Valida zona normalitzada, màxim de candidates i zona obligatòria o flexible. |
| config.py, PreparationConfig.from_dict | Resol el perfil opcional dins l’esquema de configuració i exigeix S0 activat quan es tria aquest perfil. |
| [boxes.py](boxes.py), prepare_boxes | Dona la mateixa partició S0. include_relations permet prescindir de les relacions quan la consumidora és la fase regional. |
| [regions.py](regions.py), area, overlap, xyxy | Operacions geomètriques sobre caixes i conversió de coordenades del domini. |
| regions.py, Region i _Geometry | Region porta rectangle, origen de la caixa, àncora i membres. _Geometry.from_frame construeix matrius de solapament i cobertures directes. _Geometry.proposal associa la geometria al score observat o de llavor. |
| regions.py, _strong_neighbours | Assigna febles al millor encaix fort. Les competències properes queden a les residuals. |
| regions.py, _strengthened_region | Avalua extensions observades amb suport addicional i retorna les febles amb extensió no explicada. |
| regions.py, _weak_regions | Construeix extensions delimitades a partir de grups febles densos i manté les hipòtesis aïllades. |
| regions.py, group_regions, combine_sources | Orquestra fortes i residuals. La fusió final combina fonts sense canviar la geometria representant. |
| [foreground.py](foreground.py), validate_pixels i downsample | Validació BGR uint8 i reducció a meitat de resolució amb interpolació d’àrea. |
| foreground.py, sample_indices i median_background | Selecció espaiada i mediana immutable en memòria amb les dimensions originals registrades. |
| foreground.py, foreground i component_evidence | Màscara de diferència amb llindar 27, obertura 3×3, tancament 5×5 i components de com a mínim 30 píxels. Calcula quina fracció de la caixa i del component comparteixen suport. |
| foreground.py, _RankedRegion, _in_zone i _rank | Conserva evidència i puntuació per separat, aplica pertinença de zona i ordena amb els pesos comparats al banc. |
| foreground.py, _contains i rank_regions | Aplica absorció directa després del rànquing i talla la llista. Les alternatives absorbides mantenen la procedència. |
| [representative.py](representative.py), RepresentativeBoxPreparer | Rep mostres del clip, ajusta el fons i passa cada fotograma per S0, regions i rànquing. Comprova vídeo i alineació d’imatge. |
| representative.py, _tracking_frame | Retorna les mesures actives amb IDs de candidat i fonts canòniques. Marca una extensió derivada amb source support_extent i explicita que usa el score original de la llavor. |
| [pipeline.py](pipeline.py), prepare_frame i prepare_frames | Entrades públiques. Amb aquest perfil exigeixen el preparador ajustat i els píxels corresponents. En un stream comproven que hi hagi una imatge per observació. |
| [contracts/tracking.py](../contracts/tracking.py), BoxMeasurement | Valida el nou origen support_extent. És una mesura espacial d’aquest instant. |
| [results/preparation.py](../results/preparation.py), preparation_record | Exporta totes les fonts originals, incloses les descartades al tall, a més de les candidates actives. |
| [application/tracking.py](../application/tracking.py), track_case i supply_decoded | Ajusta el fons en una primera lectura. Després reutilitza els píxels originals de l’overlay quan està actiu i informa quins índexs han format el fons. |
| [application/appearance.py](../application/appearance.py), AppearanceService | Separa el cache de ReID d’aquest perfil segons configuració i mostres de fons. Amb overlay o sense, l’extracció pot rebre la imatge descodificada ja disponible. |

### Activació i sortides

Instal·la les dependències opcionals amb `pip install -e '.[box-preparation,tracking]'`.
Per a MP4 anotat afegeix també l’extra visualization. El Docker de calibratge
ja conté les dependències necessàries.

En un pipeline existent de caixes, referencia el perfil en preparation_config.
La comanda habitual de tracking llegeix el vídeo i el CSV gravat declarat
al manifest. No torna a cridar YOLO.

```bash
python -m trampoline_vision track --config ruta/al/pipeline.json --output resultat.json
```

Per obtenir caixes i auditar-les des de Python abans de tracking:

```python
import json
from pathlib import Path

from trampoline_vision.preparation.config import PreparationConfig
from trampoline_vision.preparation.pipeline import prepare_frame
from trampoline_vision.preparation.representative import RepresentativeBoxPreparer
from trampoline_vision.results.preparation import preparation_record

config = PreparationConfig.from_dict(
    json.loads(Path("configs/preparation/representative-boxes.json").read_text())
)
preparer = RepresentativeBoxPreparer(video_id, config, background_frames)
result = preparer.prepare_with_audit(detections, bgr)
prepared = result.frame
record = preparation_record(prepared, config, audit=result)
```

El tracker rep les candidates actives. Les deteccions completes són a
prepared.source i l’auditoria independent les exporta amb preparation_record.
La traça compacta de tracking guarda les mesures actives i la seva
procedència. Cal conservar el CSV font per recuperar les altres geometries
fora d’aquella traça.

El criteri d’entrada és localitzar el gimnasta, admetent una caixa parcial
útil. La continuïtat d’ID, el comportament amb moviments de càmera i la
qualitat dels retalls per a esquelets es mesuren separadament.
[Llindars, comparadors i evidència reproduïble](../../../benchmarks/calibration/archive/detection-preparation-v1/docs/BOX_PREPARATION_STUDIES.md).

## Auditoria independent de selecció

[audit.py](audit.py) defineix `CandidateSelection`, el destí de cada regió amb
fonts originals, geometria i puntuació d’ordre, i `RepresentativePreparationResult`,
que afegeix el `TrackingFrame` i els recomptes originals → grups S0 → regions.
`RepresentativeBoxPreparer.prepare_with_audit` retorna aquest resultat;
`prepare` continua retornant només `TrackingFrame` amb les mateixes caixes.
`foreground.rank_regions_with_audit` calcula un únic rànquing i registra
`selected`, `absorbed_containment`, `candidate_limit` o `outside_hard_zone`.
En mode soft no apareix l’últim motiu. La fusió referencia l’àncora destinatària.
`results.preparation.preparation_record(..., audit=result)` exporta les decisions
com `selection_audit`, separades de la confiança YOLO i de les fonts íntegres.

La comanda següent mostra 12 fotogrames uniformes del clip, amb originals,
regions abans del tall i caixes seleccionades. No executa tracking ni YOLO.
Requereix les dependències de `box-preparation`, ffprobe i les dades locals.

```bash
PYTHONPATH=src python3 -m benchmarks.calibration review-boxes \
  --manifest data/manifests/JPN_AGE_1_000905_31.0.calibrated-boxes.example.json \
  --config configs/preparation/representative-boxes.json \
  --output runs/calibration/centered-soft-review-v1
```

Obre `index.html` de la destinació. `frames.jsonl` conté originals i decisions;
`summary.json`, configuració, hashes, mostres de fons i temps. Amb `--frames 97 180`
es poden demanar instants concrets (base zero). La sortida ha de ser nova.
Aquesta mostra visual no és una mesura exhaustiva de cobertura del gimnasta.
El temps total inclou lectura, fons, exportació JSONL i JPG; no genera MP4.
