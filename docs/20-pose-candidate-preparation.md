# 20. Preparació de candidats de tracking

## Abast d'aquest pas

El pas 3 de l'increment 2 implementa la conversió de `FrameDetections` a
`TrackingFrame`. Reutilitza els contractes de la [guia 19](19-tracking-contracts-and-backend.md)
i no executa OC-SORT. No selecciona el gimnasta ni associa identitats entre
fotogrames. El vídeo real no s'ha processat en aquest increment.

Estat posterior: la CLI `track` ja integra aquest preparador. L'execució i la
validació del recorregut complet es descriuen a la [guia 21](21-tracking-validation-guide.md).

Les funcions són reutilitzables per qualsevol font que produeixi el contracte
canònic. El càlcul anatòmic actual suporta BODY_25; incorporar altres esquemes
requereix adaptar aquest mapa, a més del corresponent lector/perception.
No s'ha implementat encara un registre general d'esquemes.

## Fitxers i responsabilitats

| Fitxer | Responsabilitat |
| --- | --- |
| `preparation/config.py` | Polítiques immutables, valors efectius i validació estricta de configuració 1.0. |
| `preparation/pose.py` | Selecció de punts, suport geomètric/anatòmic, caixa i indicador de confiança. |
| `preparation/deduplication.py` | Comparació i agrupació de propostes compatibles del mateix instant. |
| `preparation/pipeline.py` | Funcions públiques `prepare_frame` i `prepare_frames`. |
| `configs/preparation/pose-candidates.json` | Configuració llegible des de Python i referenciada pel pipeline de tracking. |

Cap d'aquests mòduls importa OpenPose, NumPy, trackers o llibreries d'imatge.
La lectura JSON estricta es reutilitza des d'`ingestion.json_io`; el domini
rep objectes, sense obrir fitxers ni generar artefactes. Els errors de
configuració produeixen `ValueError`; els de lectura mantenen `InputError`.

## Flux de dades

1. Rebre un fotograma canònic amb context, observacions i estat present/missing.
2. Per cada detecció, seleccionar punts observats i comprovar suport.
3. Calcular mesura rectangular i indicador, o conservar un candidat sense mesura.
4. Si està activada, agrupar només propostes compatibles amb totes les membres del grup.
5. Retornar candidats amb referències a les fonts originals; no assignar `track_id`.

Cada detecció d'entrada figura exactament una vegada entre les referències
dels candidats de sortida, incloses les deteccions buides o massa parcials.
`TrackingFrame.source` és la mateixa instància original, amb els punts i la
procedència intactes. No s'esborren ni s'escriuen observacions d'origen.

## Selecció de punts i suficiència

Un punt s'utilitza si és `valid`, està dins de la imatge segons `in_frame`,
té confiança positiva i arriba a `min_keypoint_confidence`. El valor inicial
0.0 admet tots els punts observats positius, encara que siguin febles.
Una coordenada zero continua sent vàlida. Els punts externs i els que no
arriben al llindar es conserven a la font, però no defineixen aquesta caixa.

La suficiència comprova aquests criteris abans d'afegir cap marge:

| Opció `box` | Inicial | Significat |
| --- | --- | --- |
| `min_keypoint_confidence` | 0.0 | Llindar inclusiu, sempre exigint confiança positiva. |
| `min_points` | 4 | Nombre mínim de punts seleccionats. |
| `min_anatomical_groups` | 2 | Nombre mínim de grups head/core/arms/legs. |
| `require_core` | true | Exigir com a mínim un punt d'ancoratge de core. |
| `min_span_px` | 1.0 | Mínim d'amplada i alçada en píxels. |
| `min_span_image_ratio` | 0.002 | Mínim d'amplada i alçada com a fracció de la diagonal d'imatge. |
| `padding_ratio` | 0.05 | Marge per cada costat, proporcional a l'amplada/alçada observades. |

Grups BODY_25: head conté nas, ulls i orelles; core conté coll, espatlles,
malucs i mid_hip; arms conté colzes i canells; legs conté genolls, turmells
i punts de peu. Diversos punts de la mateixa mà o cara no equivalen a suport
de tot el cos. Aquest mapa és una heurística de suficiència, no una garantia
d'anatomia correcta. Un punt core i un altre grup tampoc garanteixen cos complet.

Amplada i alçada han de ser positives i almenys
`max(min_span_px, min_span_image_ratio * diagonal_imatge)`. No s'imposa una
relació d'aspecte vertical ni una orientació: els casos sintètics inclouen
poses invertides i horitzontals. Això comprova la preparació geomètrica,
no la capacitat del detector per observar gimnastes en aquestes posicions.

La caixa resultant envolta els punts seleccionats. El padding s'afegeix
després de validar-la; no rescata un punt únic ni una caixa degenerada.
El resultat pot sortir del fotograma i no es retalla silenciosament.
L'origen és sempre `pose_extent`: no s'afirma que siguin límits del cos sencer.
Ni el marge ni els llindars s'han calibrat encara amb les dades reals.

## Indicador de confiança

`score_method = selected_keypoint_confidence_mean_v1` és la mitjana aritmètica
de la confiança dels punts seleccionats de la detecció representant.
Si tots tenen confiança 0.03, el score és 0.03. No s'hi afegeix un factor
perquè una persona sigui dins de la zona de trampolí, ni per semblar un salt.

El mètode és descriptiu, no calibrat: canviar el conjunt de punts o el seu
llindar pot canviar la mitjana. No és directament comparable entre models,
ni és una probabilitat d'encert. El suport s'avalua separadament; quatre
punts forts poden tenir una mitjana superior a una pose més completa i feble.

La deduplicació no suma confiances ni fa mitjana de diversos esquelets.
El futur adaptador haurà de decidir com usar aquests scores. En particular,
OC-SORT 2.6.1 exclou les mesures per sota del seu llindar d'associació: els
valors inicials d'aquesta preparació no constitueixen una configuració de tracking.
Els llindars visuals 0.25/6 tampoc intervenen en aquest mòdul.

## Deduplicació configurable

Està **desactivada per defecte** per establir primer una comparació sense
agrupacions. Activar `deduplication.enabled` executa una política conservadora
que s'haurà de calibrar amb anotacions i revisió real.

Dues propostes només són compatibles si totes dues tenen mesura i compleixen:

- IoU de les caixes **sense padding** >= `min_box_iou` (inicial: 0.7).
- Almenys `min_shared_points` noms d'articulació seleccionats compartits (inicial: 4).
- Per a **cada** punt compartit, distància <= `max_point_distance_ratio`
  multiplicat per la menor diagonal de les dues extensions (inicial: 0.08).

La comparació per noms evita identificar punts només per proximitat espacial.
La menor diagonal limita que una proposta enorme absorbeixi una de petita.
No s'intercanvien articulacions esquerra/dreta, no s'infereix la rotació
d'origen i no es pressuposa que les dades heretades conservin aquesta procedència.
Una sola articulació discrepant pot impedir agrupar: es prefereix conservar
un duplicat abans que fusionar evidència incompatible sense poder auditar-ho.

Les propostes s'ordenen per nombre descendent de punts seleccionats, després
per score descendent i finalment per ID lexical. El primer membre és el
representant. Una proposta nova només s'afegeix a un grup si és compatible
amb **tots** els seus membres. A~B i B~C no impliquen A~C.
Si encaixa en diversos grups, s'escull el primer segons aquest ordre estable;
és una heurística determinista, no una optimització global de particions.

La mesura del candidat és exactament la del representant; no es fusionen
articulacions ni caixes. `source_detection_ids[0]` identifica aquest
representant i les referències restants s'ordenen lexicalment. Els IDs són
`<frame_index>:candidate:<representative_detection_id>`, locals al fotograma.
Reordenar les deteccions sense canviar-ne IDs ni dades dona el mateix resultat.
Si es tornen a numerar les deteccions, no es promet conservar aquests IDs.

Les poses sense caixa es mantenen separades, encara que siguin dins d'una
altra caixa. Els fragments amb punts complementaris tampoc s'uneixen sense
prou punts comuns. Això deixa oberta una recuperació temporal posterior,
però evita inventar correspondències en aquesta fase.

El treball de comparació és de l'ordre de N² parelles per fotograma amb
fins a 25 punts; no requereix GPU. No s'ha mesurat encara el cost sobre els
volums reals ni la reducció efectiva de duplicats.

## Motius i limitacions dels candidats

| `issues` | Interpretació |
| --- | --- |
| `insufficient_points` | No s'arriba al recompte configurat; sense mesura. |
| `insufficient_anatomical_support` | Falten grups o ancoratge core; sense mesura. |
| `insufficient_spatial_support` | Extensió nul·la o massa petita; sense mesura. |
| `points_outside_frame` | Hi ha punts observats fora de la imatge, exclosos del càlcul. |
| `points_below_preparation_threshold` | S'han exclòs punts observats pel llindar configurat. |
| `pose_extent_only` | Mesura disponible, però només és extensió dels punts seleccionats. |
| `duplicates_grouped` | Diverses deteccions comparteixen candidat; la mesura és del representant. |

Un candidat pot tenir diversos motius. Els grups conserven la unió de
limitacions de totes les seves fonts; això no implica que cada avís pertanyi
al representant. Les dades originals permeten revisar-ne l'origen exacte.

## Ús des de Python

```python
from dataclasses import asdict
from pathlib import Path
from trampoline_vision.ingestion.json_io import read_json
from trampoline_vision.preparation.config import PreparationConfig
from trampoline_vision.preparation.pipeline import prepare_frames

config = PreparationConfig.from_dict(
    read_json(Path("configs/preparation/pose-candidates.json"))
)
effective_config = {"schema_version": "1.0", **asdict(config)}

# raw_frames és el generador FrameDetections del lector existent.
# Es consumeix un fotograma cada vegada, inclosos present buit i missing.
prepared_frames = prepare_frames(raw_frames, config)
```

Les claus desconegudes, versions no suportades, NaN/Infinity, booleans on
calen nombres i límits invàlids es rebutgen. `read_json` rebutja també claus
JSON duplicades. Els camps omesos es resolen amb defaults; `asdict` permet
registrar la configuració efectiva. El nou cas d'ús `track_case` la publica al seu informe.

Les configuracions `inspect` i `visualize` no consumeixen aquest fitxer ni
canvien el seu comportament. `track` sí que l'integra amb el backend i el registre
temporal. No hi ha una comanda de preparació aïllada provisional.

## Verificació i següent pas

Les proves cobreixen confiança baixa, coordenada zero, punts externs,
suport insuficient, padding, poses invertides, agrupacions, absència de
punts comuns, persones solapades, unions per cadena i determinisme.
Una prova d'integració connecta el lector ZIP real amb registres sintètics
i aquesta configuració, preservant fotogrames buits, missing i temps reals.

Resultat d'aquesta iteració: **68 proves correctes en Docker Linux CPU amb
Python 3.11, sense omissions**, incloses les proves existents de visualització
i dependència OC-SORT. En Python 3.10 local també passa el conjunt disponible;
7 proves s'ometen explícitament per absència d'extres o FFmpeg. Tots els
registres i vídeos utilitzats a les proves són sintètics.

Les comprovacions no demostren encara precisió sobre gimnastes reals.
Adaptador OC-SORT, registre temporal, exportació i CLI ja estan implementats
en el pas posterior. Queda revisar i calibrar el vídeo de referència amb la guia 21.
