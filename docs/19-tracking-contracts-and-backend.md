# 19. Contractes de tracking i primer backend

## Abast implementat

Aquest increment completa els passos 1 i 2 del seguiment: elecció de biblioteca,
dependència opcional i contractes d'entrada/sortida amb validacions i proves.
No executa tracking sobre OpenPose. En el pas 3 posterior ja s'han implementat
preparació de caixes i deduplicació opcional: vegeu la [guia 20](20-pose-candidate-preparation.md).
Estat posterior: adaptador, sessió d'identitats, CLI, exportació i vídeo ja estan
implementats; veure [guia 21](21-tracking-validation-guide.md). Aquest document
conserva el context de l'elecció i els contractes; la precisió real continua pendent.
La confirmació actual de naixements i la correcció 0.4.0 es descriuen a la
[guia 23](23-confirmation-fix-and-improvement-study.md), que substitueix la política del baseline 0.3.0.

L'elecció inicial és **OC-SORT mitjançant `trackers==2.6.1` de Roboflow**.
És una implementació de l'algoritme a partir de l'article, no un embolcall del
repositori original ni un model que hàgim d'entrenar. És un primer baseline a
avaluar, sense garantia encara de seguir correctament el gimnasta del cas real.
La decisió i les alternatives són a [ADR 0005](decisions/0005-ocsort-library-and-tracking-boundary.md).

## Biblioteca, API i cost

S'han comprovat les metadades i el codi de la wheel publicada el 25/09/2026,
no només la documentació `latest`, que pot avançar respecte d'aquesta versió.
La wheel `trackers-2.6.1-py3-none-any.whl` té SHA256
`b5188de630f449958be3ce787fbb0375c69cfde094b6e4b4329cd79a98108501`.

| Aspecte | Decisió o comprovació |
| --- | --- |
| Instal·lació | Extra del projecte: `pip install ".[tracking]"`. |
| Backend | `from trackers import OCSORTTracker`. |
| Entrada | `supervision.Detections` amb `xyxy` de forma N×4 i `confidence` explícita de forma N. |
| Traçabilitat | `data["candidate_id"]` conserva la referència si la sortida canvia l'ordre. |
| Temps | `update(detections, timestamp=timestamp_s)`; mantenir l'origen del clip, també en intervals. |
| Deteccions actuals | `update` retorna files actuals amb `tracker_id`; `-1` és sense identitat confirmada. |
| Estimacions vives | Propietat pública `tracked_objects`, sense confiança de detecció. |
| Identificadors | Zero és un ID vàlid; `-1` mai es converteix en una identitat del domini. |
| Canvi de vídeo | Nova instància o `reset`; no compartir estat entre treballs. |
| Imatge | OC-SORT 2.6.1 ignora `frame`; aquest recorregut no necessita píxels ni GPU. |

La distribució exigeix Python >=3.10. Les dependències obligatòries declarades
són NumPy >=2.0.2, Supervision >=0.26.1, SciPy >=1.13.1, OpenCV-Python >=4.8.0,
Rich >=13, Requests >=2.28 i pyDeprecate >=0.8. No instal·lem els extras
`detection`, `mask` o `tune`: no calen detectors, pesos, Torch ni serveis remots
per a aquesta prova. El nucli del projecte continua sense aquestes dependències.

És un extra amb dependències numèriques i visuals apreciables; s'instal·la en
Docker o en un entorn virtual, sense actualitzar el NumPy de l'entorn antic de
TFM. La versió del backend està fixada, però això **no és un lock complet**:
les transitives encara es resolen segons plataforma i versió Python. Per a un
desplegament reproduïble caldrà congelar-les i conservar les seves llicències.

La biblioteca està publicada sota Apache 2.0. Les dependències directes tenen
llicències permissives (NumPy/SciPy BSD, Supervision MIT, OpenCV Apache 2.0,
Rich MIT, Requests Apache 2.0 i pyDeprecate Apache 2.0). Això no substitueix
l'inventari de la imatge distribuïda: wheels com OpenCV poden incloure altres
components i avisos que cal conservar. No es canvia la llicència del projecte.

## Límits que condicionen el futur adaptador

**Confiança baixa.** En aquesta versió, OC-SORT exclou de l'associació i de la
creació de tracks les deteccions per sota de `high_conf_det_threshold`.
Les retorna amb ID -1. No té la segona passada de confiança baixa de ByteTrack.
Si no es proporciona confiança, la biblioteca assumeix 1: l'adaptador haurà
d'enviar sempre l'indicador explícit i documentar-ne el càlcul.

Per tant, aquesta elecció no implementa encara una política de «mesura feble
per mantenir, mesura forta per crear». Si les proves mostren que és necessària,
compararem ByteTrack, disponible a la mateixa biblioteca, o una política
explícita d'admissió. No direm que baixar un llindar resol la pèrdua de focus.

**Temps.** `delta_t` és la distància històrica en fotogrames utilitzada per
calcular direcció; no és el temps transcorregut en segons. Els timestamps són
el mecanisme temporal separat. `lost_track_buffer` s'expressa en unitats de
fotograma a 30 FPS; amb timestamps, el pressupost temporal és buffer/30 segons.
El futur adaptador haurà de convertir una política de domini en segons i provar
la frontera d'expiració. No ometrà els fotogrames buits. La prova actual usa
intervals irregulars curts i un buit llarg; encara no és un benchmark VFR.

**Estats.** La biblioteca exposa deteccions i estimacions, però no el nostre
registre complet de cicle de vida. L'adaptador haurà de mantenir la darrera
observació real, gestionar confirmacions i emetre desaparicions/finalitzacions.
No es llegiran atributs privats per fer-ho. La confirmació inicial i els IDs -1
necessiten una política expressa abans d'emetre identitats provisionals.

**Pose parcial.** Un rectangle que envolta tres punts d'un braç no és una
caixa fiable del gimnasta sencer. El contracte distingeix `pose_extent` de caixa
de detector, i permet conservar candidats sense mesura rectangular.
L'associació per caixes encara no consumeix aquests candidats parcials.

## Contractes implementats

Fitxer: [contracts/tracking.py](../src/trampoline_vision/contracts/tracking.py).
Són dataclasses immutables, sense imports de NumPy, Supervision o trackers.
`TRACKING_SCHEMA_VERSION = "1.0"` versiona la semàntica interna; encara no hi ha
serialitzador ni esquema d'API pública de tracking.

| Tipus | Necessitat que resol |
| --- | --- |
| `BoundingBox` | Caixa xyxy finita, d'àrea positiva, en píxels originals; sense retall implícit. |
| `BoxMeasurement` | Caixa mesurada, origen detector/pose_extent, score [0,1] i mètode del score. |
| `TrackingCandidate` | ID local, referències originals, mesura opcional i limitacions explícites. |
| `TrackingFrame` | Context/font originals més candidats; valida referències i evita duplicar evidència. |
| `TrackSample` | ID temporal opac, estat, observació/predicció, caixa opcional i últim temps observat. |
| `TrackingFrameResult` | Entrada exacta, estats i partició explícita de candidats assignats/sense assignar. |

`source_detection_ids` permet que preparation agrupi diverses deteccions
multirotades. Una detecció no pot alimentar dos candidats. Agrupar-les no
modifica ni fusiona automàticament les articulacions originals. Les observacions
que no tenen candidat també continuen disponibles a `TrackingFrame.source`.
El preparador del pas 3 implementa una primera política d'agrupació conservadora
i no exclou cap detecció de les referències dels candidats. Encara no està calibrada.

Un candidat sense mesura necessita un motiu, per exemple
`insufficient_spatial_support`. Un score zero és vàlid i es conserva. Els
llindars visuals de `RenderStyle` no formen part d'aquests contractes.
`score_method` explica com s'ha obtingut l'indicador; no el fa comparable entre models.

`track_id` és text opac dins d'un vídeo i d'una execució. L'adaptador podrà
convertir l'ID zero en `ocsort:0`. No és el número de persona al JSON.
Els estats admesos són `tentative`, `active`, `lost` i `finished`; aquesta
enumeració defineix el vocabulari, però no executa la màquina d'estats.

Una mostra `observed` exigeix un candidat amb mesura actual, la mateixa caixa
mesurada i `last_observed_timestamp_s` igual al timestamp actual. La caixa
filtrada del Kalman no pot substituir silenciosament aquesta mesura.
Una mostra `predicted` no referencia cap candidat actual, té una darrera
observació estrictament anterior i pot portar caixa estimada o None. Les poses
es recuperen de la font original; no es reemeten punts predits com a observats.

Les assignacions són unívoques. Els candidats sense caixa també consten entre
els no assignats. El resultat rebutja IDs inexistents, assignacions dobles,
caixes observades inventades i candidats que desapareixen de la partició.
La validació dels contractes és per fotograma. El nou `tracking/session.py`
completa aquesta frontera amb ordre temporal, no reutilització d'IDs finalitzats,
registre de l'última observació i transicions de vida. Veure la guia 21.

## Exemple de flux, encara sense algoritme

```python
from trampoline_vision.contracts.tracking import (
    BoundingBox, BoxMeasurement, TrackSample, TrackingCandidate,
    TrackingFrame, TrackingFrameResult,
)

# raw_frame és un FrameDetections del lector actual, sense modificar-lo.
# Les coordenades i el score d'aquest exemple són didàctics, no un preparador.
candidate = TrackingCandidate(
    candidate_id="c0",
    source_detection_ids=(raw_frame.detections[0].detection_id,),
    measurement=BoxMeasurement(
        bbox=BoundingBox(100, 80, 140, 150),
        source="pose_extent", score=0.15, score_method="example_only",
    ),
)
frame = TrackingFrame(source=raw_frame, candidates=(candidate,))

# Representació d'una assignació que haurà de decidir el futur tracker.
sample = TrackSample(
    track_id="ocsort:0", state="active", evidence="observed",
    bbox=candidate.measurement.bbox, candidate_id="c0",
    last_observed_timestamp_s=raw_frame.context.timestamp_s,
)
result = TrackingFrameResult(frame=frame, tracks=(sample,), unassigned_candidate_ids=())
```

Responsabilitats del recorregut que construirem:

1. `ingestion` produeix `FrameDetections` del vídeo i dels JSON existents.
2. `preparation` produirà `TrackingFrame`: agrupació, caixes justificades i indicadors.
3. Un adaptador de `tracking` convertirà només mesures admissibles a l'API externa,
   avançarà tots els instants i produirà `TrackingFrameResult` amb traçabilitat.
4. `subjects` seleccionarà el gimnasta sobre trajectòries; `results` les representarà.
5. `segmentation` consumirà seguiment i qualitat per delimitar salts; puntuació vindrà després.

## Proves i execució

Les proves unitàries de contractes no requereixen cap extra. L'extra només
afegeix una prova d'integració amb caixes sintètiques: API, ordre/referències,
IDs, timestamps irregulars, fotograma buit, recuperació, baixa confiança i reset.
No és el tracker del projecte ni prova que una identitat sigui correcta al vídeo real.

```powershell
docker compose --profile tracking build tests-tracking
docker compose --profile tracking run --rm tests-tracking
```

El target `test-tracking` amplia el target de proves CPU i no munta TFM ni `runs`.
El servei `replay` continua sent el recorregut d'inspecció/visualització.
Sense l'extra, la prova de dependència s'omet explícitament.

Verificació d'aquest increment: 48 proves correctes en Docker Linux CPU amb
Python 3.11, sense omissions. El cas real de TFM no s'ha processat en aquest
increment. Versions resoltes en aquesta verificació: trackers 2.6.1,
Supervision 0.31.2, NumPy 2.4.6, SciPy 1.17.1, OpenCV-Python 5.0.0.93,
Rich 15.0.0, Requests 2.34.2 i pyDeprecate 0.13.0. És el registre d'una
execució, no un fitxer de bloqueig. En Python 3.10 local les proves de domini
també passen; les d'extres absents i FFmpeg s'ometen explícitament.

## Continuació implementada

1. Completat al pas 3: preparació de candidats, caixes, score documentat i
   deduplicació configurable, mantenint la font; guia 20. Revisió real pendent.
2. Completat: adaptador OC-SORT, registre d'identitats i proves de seqüència.
3. Completat: configuració i cas d'ús amb exportació/visualització de tracking.
4. Només aleshores executar i revisar el vídeo real, amb criteris explícits
   de pèrdua, recuperació i canvi d'identitat; comparar ByteTrack si cal.

Fonts primàries: [distribució 2.6.1](https://pypi.org/project/trackers/2.6.1/),
[API de tracking](https://trackers.roboflow.com/latest/api/trackers/),
[temps variable](https://trackers.roboflow.com/latest/learn/dynamic-frame-rate/),
[repositori original OC-SORT](https://github.com/noahcao/OC_SORT).
Els detalls específics anteriors s'han contrastat amb la wheel fixada.
