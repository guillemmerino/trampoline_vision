# 04. Contractes de dades

Versió implementada per al recorregut d’entrada: 1.0. `contracts/observations.py` defineix
`VideoAsset`, `FrameContext`, `KeypointObservation`, `DetectionProvenance`, `PersonDetection` i
`FrameDetections` amb validació i dataclasses immutables. BODY_25 té 25 noms fixos. Els contractes
de selecció, salts i avaluació de la taula continuen sent propostes de vocabulari.
`contracts/tracking.py` implementa també la frontera de preparació/seguiment 1.0:
`BoundingBox`, `BoxMeasurement`, `TrackingCandidate`, `TrackingFrame`, `TrackSample`
i `TrackingFrameResult`. Semàntica i invariants a la [guia 19](19-tracking-contracts-and-backend.md).
La [preparació inicial](20-pose-candidate-preparation.md) ja produeix candidats;
el [recorregut de tracking](21-tracking-validation-guide.md) produeix identitats i exportacions.

## Convencions comunes

- `video_id` identifica l'entrada; `run_id` identifica l'execució sobre aquella entrada.
- `frame_index` intern és zero-based i correspon al vídeo descodificat.
- `timestamp_s` és el temps de presentació relatiu a l'inici del clip analitzat.
- Per a FPS constants, el temps pot derivar-se de l'índex i FPS verificats; per a FPS variables
  calen marques temporals. No s'assumeix sempre 30 FPS.
- Coordenades base: píxels del fotograma original, origen superior esquerre, X cap a la dreta,
  Y cap avall. Les transformacions de visualització no alteren aquestes dades.
- Els intervals temporals són `[start_s, end_s)`. `end_s` pot coincidir amb el final del vídeo.
- Les dades absents són explícites; no s'utilitzen NaN o Infinity en JSON públic.
- Els identificadors només són únics dins de l'àmbit declarat. Un `detection_id` no és un `track_id`.

## Vocabulari de contractes (implementació parcial)

| Contracte | Camps essencials i semàntica |
| --- | --- |
| `VideoAsset` | ID, referència de font, dimensions, durada, FPS o base temporal, recompte de fotogrames i transformacions prèvies conegudes. |
| `FrameContext` | Vídeo, índex, temps i dimensions; existeix també si no hi ha deteccions. |
| `SkeletonSchema` | ID i versió, noms ordenats de punts, parelles anatòmiques i equivalències documentades. |
| `KeypointObservation` | Nom/índex semàntic, X, Y, confiança opcional, validesa i procedència. |
| `PersonDetection` | ID de detecció, context de fotograma, esquelet, punts, caixa opcional, confiança global opcional i origen del backend. |
| `FrameDetections` | Context i llista de deteccions; la llista pot ser buida. |
| `TrackSample` | Implementat: ID temporal, estat, tipus d'evidència, caixa, candidat i últim temps observat; context al resultat que el conté. |
| `PersonTrack` | Seqüència temporal de mostres d'una identitat i esdeveniments del seu cicle de vida. |
| `SubjectSelection` | Candidats, trajectòries seleccionades, política, evidències i estat resolt/ambigu. |
| `JumpSegment` | ID de segment, subjecte/trajectòria, inici/final, límits incerts, fases opcionals i qualitat. |
| `AnalysisResult` | Entrada, execució, configuració resolta, trajectòries, subjectes, segments, qualitat, avaluacions i artefactes. |

## Articulacions i confiances

L'esquema BODY_25 conserva els seus 25 punts, encara que alguns faltin. No es descarten columnes
perquè siguin constants en un clip. Un esquema diferent té un ID diferent; el consumidor declara
quins punts necessita. Les equivalències aproximades no s'etiqueten com a observacions exactes.

`confidence` ha de quedar dins del rang declarat pel backend després de la conversió, però no
es pressuposa calibrada ni comparable entre models o orientacions. Una coordenada zero pot ser
vàlida; la màscara i la confiança determinen com tractar-la. Si no hi ha un punt observat, les
seves coordenades poden ser null a la serialització. Una predicció no augmenta la cobertura observada.

## Geometria i transformacions

La caixa adopta `[x_min, y_min, x_max, y_max)` amb àrea positiva. Les caixes derivades d'articulacions
es distingeixen de les de detector. Crops, padding, redimensionament i rotació han de conservar
la transformació i la seva inversa. Una normalització per algoritme declara les seves unitats;
no es poden calcular angles en una escala anisòtropa sense corregir-la.

## Detall del lector implementat

Cada fotograma intern conté `context`, `detections` i `source_status`. `present` amb llista buida
indica un JSON amb `people: []`; `missing` indica que manca el registre d’origen i no equival a una
detecció negativa. `valid` significa observat amb confiança positiva, no una garantía d’exactitud.
`in_frame` informa de punts fora de la imatge sense retallar-los. Els punts absents tenen X/Y i
`in_frame` null. El lector no calcula caixes; el preparador posterior pot obtenir
una `pose_extent` amb procedència i suficiència explícites.

Els temps de presentació es llegeixen amb ffprobe, es normalitzen al primer fotograma i es conserva
`source_start_s`. La durada final prové del paquet/fotograma si està disponible; un fallback a
diferències de temps o FPS s’indica amb un avís.

## Identitat i buits

Una trajectòria pot tenir mostres sense detecció. Al contracte implementat, `evidence`
distingeix `observed` i `predicted`; només observed pot referenciar un candidat actual.
Una recuperació pot unir fragments només amb evidència i un esdeveniment explícit; les trajectòries
originals es poden auditar. Un segment no canvia de persona perquè un altre candidat tingui més
confiança en un fotograma. La selecció del subjecte pot referenciar fragments reconciliats.

## Proveniència i versions

Cal conservar versió del contracte, backend i pesos quan es coneguin, configuració efectiva,
transformacions, IDs originals i advertiments de conversió. En dades heretades, la procedència
desconeguda es declara com a desconeguda. Els canvis de semàntica requereixen nova versió i una
conversió explícita; la forma d'un array no és suficient per inferir el seu significat.
