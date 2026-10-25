# 21. Executar, validar i millorar el tracking

## Estat real del lliurable

Ja existeix el recorregut executable complet de deteccions enregistrades:
ingestió → preparació → OC-SORT → registre d'identitats → JSONL/informe i
vídeo opcional. També hi ha una comanda de diagnòstic amb anotacions manuals.
El codi i les proves utilitzen els mateixos contractes i no depenen del clip de
referència. El baseline real 0.3.0 i la correcció 0.4.0 estan documentats als
[estudis 22](22-first-tracking-baseline-review.md) i [23](23-confirmation-fix-and-improvement-study.md).

La validació sintètica comprova funcionament, temps, procedència i publicació.
No demostra encara precisió sobre gimnastes petits, invertits o parcialment
observats. L'increment de tracking queda tècnicament preparat; la seva acceptació
sobre les dades reals continua pendent. Selecció del gimnasta i salts vindran després.

La versió actual és 0.4.0. La verificació cobreix 95
proves a Docker Linux CPU amb Python 3.11, inclosa la dependència real i vídeos
sintètics. Cap d'aquestes proves utilitza el vídeo original de TFM.

## Preparar l'entorn

Des de l'arrel del projecte, amb Docker Desktop Linux:

```powershell
New-Item -ItemType Directory -Force runs | Out-Null
docker compose --profile tracking build tracking tests-tracking
docker compose --profile tracking run --rm tests-tracking
```

`tracking` hereta de `replay` els muntatges de TFM només lectura i `runs` per
a sortides. `tests-tracking` no munta ni TFM ni `runs`. El runtime CPU bàsic
continua disponible per a inspecció i visualització sense instal·lar OC-SORT.
Fora de Docker: entorn virtual nou amb `pip install ".[tracking,visualization]"`
i FFmpeg/ffprobe al PATH. No actualitzar l'entorn antic de TFM.

## Executar una prova real

Començar amb tres segons i noms nous per a cada execució:

```powershell
docker compose --profile tracking run --rm tracking track --config configs/pipelines/track-openpose.json --start 0 --end 3 --output runs/tracking-baseline-01.json --video-output runs/tracking-baseline-01.mp4
```

Es generen informe JSON, `tracking-baseline-01.frames.jsonl` i MP4 sense àudio.
Es rebutgen sortides existents i rutes coincidents amb entrades. L'informe es
publica al final; errors abans de publicar no deixen artefactes finals. Si falla
una còpia posterior, es retiren els fitxers publicats per la mateixa execució.
Una interrupció del procés encara pot deixar fitxers parcials: no és una transacció
de filesystem. Un informe final absent significa execució no confirmada.

Per analitzar la fase de vol coneguda, sense reiniciar la identitat a mig vídeo:

```powershell
docker compose --profile tracking run --rm tracking track --config configs/pipelines/track-openpose.json --start 14 --end 17 --output runs/tracking-flight-01.json --video-output runs/tracking-flight-01.mp4
```

Es processen per escalfament els fotogrames anteriors a 14 s. No es consulta
el futur després del límit final; no hi ha suavitzat retrospectiu. El JSONL
exporta només el tram seleccionat, amb índexs i timestamps originals. El MP4
comença a zero i la capçalera mostra el temps de la font. Per al clip complet,
ometre `--start` i `--end`. Per estudiar només dades, ometre `--video-output`.

## Què significa cada estat

- Les deteccions amb ID extern -1 encara no tenen ID públic del backend. Queden
  com a candidats sense assignar; no es creen IDs provisionals a partir de la
  seva posició a l'array ni es reconstrueixen identitats passades silenciosament.
- `active`/`observed`: mesura actual assignada. La caixa és la del candidat,
  no la caixa filtrada del Kalman. Les articulacions dibuixades són les originals
  de la detecció representant, sense fusió de membres de diverses persones.
- `lost`/`predicted`: identitat encara viva sense mesura actual. Porta caixa
  estimada si és finita i vàlida, però no articulacions ni confiança observada.
- `finished`/`predicted`: el backend ha eliminat la identitat. S'emet una sola
  mostra de tancament, sense caixa, i no es permet reutilitzar aquell ID a la sessió.

Es registren esdeveniments `confirmed`, `lost`, `recovered` i `finished` amb
temps original. `tentative` és part del vocabulari del contracte, però aquest
adaptador no l'emet: els IDs externs pendents es mantenen interns fins a
confirmar-los. `confirmation_frames` controla la ratxa de naixement al domini,
amb política `birth_streak_v1`. El mínim intern d'OC-SORT és 1, de manera que
una recuperació d'identitat coneguda no es reconfirma. La primera detecció -1
no suma a la ratxa perquè encara no sabem a quin ID pertany. Veure guia 23.

Una sessió exigeix inici a índex/temps zero, fotogrames consecutius, temps
estrictament creixents i vídeo/dimensions constants. Per canviar de vídeo,
configuració o repetir una prova es crea una sessió nova. Si falla després de
tocar el backend, no s'intenta continuar una sessió parcialment mutada.

Les identitats vives al límit de tall o final de vídeo s'indiquen a
`right_censored_track_ids`; no s'inventa una desaparició física. Les dades de
tracks del resum inclouen escalfament i ho indiquen explícitament; totals i
esdeveniments de l'interval exportat només corresponen a aquell interval.

## Llegir les sortides

El JSONL conté un registre per fotograma seleccionat:

| Camp | Utilitat |
| --- | --- |
| `schema_version`, `run_id`, `context` | Identificar execució, vídeo, índex, temps i geometria. |
| `source_status`, `source_detections` | Distingir absència de JSON i absència de persones. |
| `candidates` | Mesura, score, mètode, limitacions, IDs originals i procedència. |
| `tracks` | ID persistent, estat, evidència, caixa i últim temps realment observat. |
| `unassigned_candidate_ids` | Partició completa de candidats no associats, inclosos els sense caixa. |
| `events` | Transicions detectades en aquest instant. |

Els motius no assignats són `no_measurement`, `below_threshold` i
`unconfirmed_or_unmatched`. L'últim no distingeix causes que l'API pública no
exposa; no es presenta un motiu més precís del que sabem.

El JSONL no duplica totes les articulacions: es poden recuperar dels JSON
originals o de l'exportació d'observacions d'`inspect`. Les referències originals
permeten veure si una pèrdua és del model, de la preparació o de l'associació.

L'informe desa configuració efectiva, versions, rang, escalfament, incidències,
comptatges, tracks i identitats obertes. Els JSON petits tenen hash; vídeo i
ZIP/carpeta tenen ruta, mida i mtime. Això no és una identitat immutable del
contingut; un benchmark formal haurà de fixar hashes de tot el corpus.

El vídeo mostra caixa contínua per observació i discontínua per predicció,
amb el mateix color/ID entre fotogrames. La paleta és finita: el color sol no
identifica inequívocament una persona. Es dibuixen les poses observades, també
febles, sense aplicar els llindars 0.25/6 del visor filtrat. Les coordenades
exportades no es retallen; només el dibuix de la caixa s'ajusta als límits.

## Revisió manual i diagnòstic mesurable

Primer revisar vídeo original/overlay d'observacions i tracking conjuntament.
Anotar el gimnasta en instants repartits entre posició dreta, vol, inversió,
aterratge, parcialitat i absències. Afegir entrenadors/jutges en possibles
confusions. Triar una detecció original que realment correspon al subjecte,
sense donar per bona la identitat assignada pel tracker.

Desar, per exemple, `runs/annotations-review-01.json`. Aquesta plantilla és
didàctica: els índexs i IDs s'han de substituir pels revisats, no copiar com
a veritat terreny del clip real:

```json
{
  "schema_version": "1.0",
  "video_id": "ID_DEL_CAS",
  "samples": [
    {"frame_index": 20, "subject_id": "gymnast", "source_detection_id": "20:7"},
    {"frame_index": 35, "subject_id": "gymnast", "source_detection_id": null},
    {"frame_index": 50, "subject_id": "gymnast", "source_detection_id": "50:3"}
  ]
}
```

`null` indica persona visible sense proposta identificable. Una detecció
identificable però massa parcial s'anota amb el seu ID: si no acaba assignada,
comptarà com una absència observada. No anotar com visible un subjecte que no
es pot verificar. Cada subjecte té com a màxim una mostra per fotograma;
una detecció no pot ser veritat terreny de dos subjectes.

La comanda següent només llegeix l'exportació i les anotacions, sense inferir
ni tornar a executar el vídeo:

```powershell
docker compose --profile tracking run --rm tracking evaluate-tracking --tracks runs/tracking-baseline-01.frames.jsonl --annotations runs/annotations-review-01.json --output runs/evaluation-baseline-01.json
```

Retorna cobertura observada sobre mostres anotades, IDs diferents per subjecte,
canvis d'ID entre matches revisats i subjectes que comparteixen un ID al mateix
instant. Les prediccions mai compten com a matches observats. Els canvis entre
matches es compten també si hi ha misses entremig; l'informe conserva els dos
índexs per interpretar-los. Això **no és HOTA, IDF1, MOTA ni una mesura de tots
els errors del vídeo**. Els canvis no observats entre anotacions poden escapar.

Es rebutgen anotacions duplicades, un altre video_id, instants no exportats,
IDs originals inexistents i exportacions discontínues o barrejades de diversos
runs. Les mateixes anotacions es poden reutilitzar entre configuracions si
les observacions d'entrada i els seus IDs són exactament els mateixos.

## Comparar i millorar sense perdre el baseline

1. Conservar el baseline amb deduplicació desactivada i un nom de sortida únic.
2. Registrar on es perd l'observació: model, manca de caixa, llindar del tracker,
   confirmació o canvi d'identitat. El recompte global de tracks no resol aquesta pregunta.
3. Copiar la configuració i canviar una família de criteris cada vegada.
4. Executar el mateix interval i les mateixes anotacions; comparar cobertura,
   canvis d'ID i unions incorrectes, a més de la revisió visual.
5. Un canvi només s'accepta si millora els casos difícils sense degradar els
   casos clars. Afegir el cas sintètic reproduïble o fixture anotada corresponent.

| Paràmetre | Efecte a comprovar |
| --- | --- |
| `box.*` de preparació | Si es perden poses petites/parcials o s'accepta soroll sense suport. |
| `deduplication.enabled` i llindars | Duplicats residuals i persones diferents agrupades indegudament. |
| `confidence_threshold` | Amb 0.1, una mesura 0.03 queda fora; baixar-lo també pot crear tracks de soroll. |
| `confirmation_frames` | Naixements espuris i retard de primera identitat confirmada. |
| `max_lost_s` | Recuperació curta davant de reassignacions incorrectes després d'un buit llarg. |
| `min_iou` | Desplaçaments grans i canvis de caixa contra confusions entre persones properes. |
| `direction_weight`, `velocity_lookback_frames` | Consistència en canvis de direcció, inversions i aterratges. |

Els valors del fitxer inicial són hipòtesis no calibrades. `max_lost_s` es
converteix a `ceil(segons*30)` unitats de la biblioteca i el pressupost efectiu
es registra a l'informe. `velocity_lookback_frames` és història de direcció,
no un delta de temps físic. Sempre s'envien timestamps, també amb FPS variables.

OC-SORT 2.6.1 no té una passada diferenciada de deteccions febles per mantenir
tracks. Si aquesta limitació pesa més que els seus avantatges, el següent
experiment serà un adaptador ByteTrack amb els mateixos contractes i anotacions;
encara no s'ha implementat. Tampoc hi ha ReID, recuperació amb píxels, fusió
retrospectiva de fragments ni selecció automàtica del gimnasta en aquest lliurable.

## Ordre de lectura del codi

1. `tracking/config.py`, `backend.py` i `session.py`: biblioteca i registre temporal.
2. `ingestion/tracking_config.py`: configuració executable i resolució de rutes.
3. `application/tracking.py`: recorregut, informes i publicació.
4. `results/tracking.py` i `results/video.py`: exportació, dibuix i codificació compartida.
5. `application/tracking_evaluation.py`: diagnòstics sobre anotacions.
6. `tests/unit/test_tracking_session.py`, `test_tracking_evaluation.py`,
   `test_tracking_overlay.py` i `tests/integration/test_tracking.py`.

Fonts de la dependència: [trackers 2.6.1](https://pypi.org/project/trackers/2.6.1/)
i [API pública](https://trackers.roboflow.com/latest/api/trackers/). Les proves
d'integració contrasten la versió fixada; `latest` pot evolucionar separadament.
