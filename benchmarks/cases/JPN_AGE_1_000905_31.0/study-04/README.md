# Estudi 04 — Caixes de persona independents

Reprodueix les deteccions YOLO històriques del clip complet i contrasta
OC-SORT i ByteTrack amb les mateixes anotacions visuals de l'estudi 03.
No executa inferència, retalls per a OpenPose, associació de poses ni puntuació.
Resultats i interpretació al [document 25](../../../../docs/25-independent-box-tracking-study.md).

## Fitxers

| Fitxer | Responsabilitat |
| --- | --- |
| `replay_boxes.py` | Valida el CSV i envia caixes, confiança i temps originals a la sessió de tracking. |
| `analyze_boxes.py` | Compara cobertura i identitats amb caixes visuals disperses i assignació unívoca. |
| `render_boxes.py` | Exporta MP4 verificat i trajectòria CSV sense unir IDs ni ocultar prediccions. |
| `contact_sheet.py` | Genera làmines per revisar identitats amb el vídeo original. Requereix OpenCV i Pillow. |
| `review-notes.json` | ID i tram seleccionats manualment, prediccions, caixes ambigües i contraexemples. |
| `results.json` | Configuracions efectives, SHA del CSV, resultats dels set controls i informe de la mostra. |

L'adaptador experimental ByteTrack s'importa de `../study-03/explore.py`.
El paquet de producció continua treballant amb el seu registre de backends actual.
Els punts canònics del replay són explícitament absents: cap pose no es fabrica.
Les eines exigeixen paquet 0.4.0 i el runtime fixat `trackers==2.6.1`.

## Reproducció des de l'arrel del projecte

Amb Docker Compose i TFM com a projecte germà. Construir el runtime actual:

```powershell
docker compose --profile tracking build tracking
```

El muntatge addicional de `benchmarks` és de lectura. Les sortides s'escriuen
a `runs/`; es rebutgen carpetes de sortida existents. Canviar-ne el nom
per repetir una execució, conservant els resultats anteriors.

```powershell
docker compose --profile tracking run --rm -v "${PWD}/benchmarks:/benchmarks:ro" --entrypoint python tracking /benchmarks/cases/JPN_AGE_1_000905_31.0/study-04/replay_boxes.py --manifest data/manifests/JPN_AGE_1_000905_31.0.example.json --boxes /workspace/TFM/Tracking_system/output_videos/JPN_AGE_1_000905_31.0_bboxes.csv --output-dir runs/tracking-yolo-replay
```

Per executar els quatre controls de llindars, afegir
`--variants ocsort_low ocsort_iou002 ocsort_low_iou002 ocsort_low_iou002_dir0`
i utilitzar una altra carpeta de sortida. La variant `byte_boxes_weak`
exigeix naixements forts, però admet confiança 0,02 per mantenir IDs confirmats.
Els controls `ocsort_low*` sí que abaixen el llindar general; no es confonen
amb la política de naixement fort de ByteTrack.

Analitzar els tres replays principals:

```powershell
docker compose --profile tracking run --rm -v "${PWD}/benchmarks:/benchmarks:ro" --entrypoint python tracking /benchmarks/cases/JPN_AGE_1_000905_31.0/study-04/analyze_boxes.py --runs runs/tracking-yolo-replay --case-dir /benchmarks/cases/JPN_AGE_1_000905_31.0 --output runs/tracking-yolo-replay/diagnosis.json
```

Exportar el vídeo complet amb totes les identitats:

```powershell
docker compose --profile tracking run --rm -v "${PWD}/benchmarks:/benchmarks:ro" --entrypoint python tracking /benchmarks/cases/JPN_AGE_1_000905_31.0/study-04/render_boxes.py --manifest data/manifests/JPN_AGE_1_000905_31.0.example.json --boxes /workspace/TFM/Tracking_system/output_videos/JPN_AGE_1_000905_31.0_bboxes.csv --records runs/tracking-yolo-replay/ocsort_boxes.frames.jsonl --output-dir runs/tracking-yolo-replay/all-actors
```

Exportar la mostra revisada de l'ID `ocsort:36`, sense ajuntar identitats:

```powershell
docker compose --profile tracking run --rm -v "${PWD}/benchmarks:/benchmarks:ro" --entrypoint python tracking /benchmarks/cases/JPN_AGE_1_000905_31.0/study-04/render_boxes.py --manifest data/manifests/JPN_AGE_1_000905_31.0.example.json --boxes /workspace/TFM/Tracking_system/output_videos/JPN_AGE_1_000905_31.0_bboxes.csv --records runs/tracking-yolo-replay/ocsort_boxes.frames.jsonl --output-dir runs/tracking-yolo-replay/sample --first 400 --stop 487 --track-id ocsort:36 --review /benchmarks/cases/JPN_AGE_1_000905_31.0/study-04/review-notes.json
```

La selecció d'ID i d'interval és manual i posterior a la prova. No és un
selector automàtic del gimnasta. La mostra conté 80 observacions i 7
prediccions; 7 de les observacions tenen caixes ambigües marcades. El mateix
ID canvia d'actor fora del tram: no extrapolar la mostra a tot el vídeo.

L'anàlisi geomètrica utilitza anotacions aproximades i disperses, sense
revisió humana independent. Els comptadors de canvis d'ID només descriuen
els instants anotats. La revisió visual aporta contraexemples intermedis
que aquests comptadors no poden capturar.
