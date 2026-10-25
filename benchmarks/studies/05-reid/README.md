# Estudi 05 — Tracking amb aparença visual

Compara OC-SORT, BoT-SORT sense ReID i el mateix BoT-SORT amb OSNet
preentrenat. Tres vídeos complets, caixes YOLO enregistrades, tots els actors,
càmera fixa i cap inferència nova de detector o pose. Interpretació i límits
al [document 26](../../../docs/26-reid-tracking-comparison.md).

## Resultat

Als instants revisats, els canvis mínims entre matches passen de 17 a 7,
de 12 a 6 i d'11 a 7 entre OC-SORT i ReID. Són límits inferiors de pilot,
no canvis exhaustius del vídeo. La cobertura observada no millora en els
tres clips i la identitat encara es fragmenta. No s'ha canviat el backend
de producció. L'associació amb articulacions continua pendent.

## Fitxers

| Fitxer | Responsabilitat |
| --- | --- |
| `protocol.json` | Casos i paràmetres fixats abans de comparar les sortides. |
| `Dockerfile` | Runtime CPU separat, amb parella PyTorch/Torchvision compatible. |
| `requirements-frozen.txt` | 61 restriccions de versió capturades del runtime efectiu. |
| `prepare_weights.py` | Descàrrega pública temporal i comprovació del SHA abans de publicar pesos. |
| `run_study.py` | Cache ReID, port BoT-SORT i sessió comuna de confirmació/vida. |
| `smoke_port.py` | Controls sintètics de naixement, evidència feble, recuperació, expiració i ordre de candidats. |
| `prepare_review.py` | Làmines i plantilla de referències des del vídeo, sense mostrar trackers. |
| `review-reference-v1.json` | Anotació inicial conservada. |
| `review-reference.json` | Revisió 2, 178 instants i duplicats acceptables; no revisió humana independent. |
| `reference-corrections.json` | Set correccions posteriors explícites, aplicades igual a totes les variants. |
| `reference-inputs.json` | Vinculació de candidats als SHA de vídeo i CSV originals. |
| `evaluate_study.py` | Matches, ambigüitats, mínim de canvis entre mostres i diagnòstic de descriptors. |
| `audit_recovery.py` | Buits d'un mateix ID i contraexemples visuals del jutge. |
| `render_comparison.py` | MP4 comparatiu amb PTS verificats i CSV de totes les identitats. |
| `results.json` | Resultats petits, versions i verificacions reproduïbles. |

El port reutilitza l'adaptador CSV de `cases/JPN_AGE_1_000905_31.0/study-04`.
Les coordenades de pose són absents explícites. `det_id` és local al fotograma;
cap associació temporal es dedueix d'aquest índex. Els IDs públics retornats
per BoxMOT es relacionen amb candidats mitjançant `det_ind`, no per ordre
de files de sortida ni per un segon matching de caixes.

La vida segueix les llistes públiques d'associació de BoxMOT 16.0.9, incloent
el seu tick transitori de retirada. El buffer de 15 fotogrames és nominal;
veure el límit d'expiració al document 26. Aquest és un port experimental,
no un nou registre de backends del paquet.

## Entorn i muntatges

Des de l'arrel del projecte, amb TFM com a germà. No s'envien vídeos a cap
servei. La descàrrega inicial només obté dependències i pesos públics.
`runs/` ha d'existir. Les dades de TFM i el codi del benchmark es munten
de lectura; les sortides i el cache són locals a `runs/`.

```powershell
docker compose --profile tracking build tracking
docker build --build-arg BASE_IMAGE=trampoline-vision:tracking -f benchmarks/studies/05-reid/Dockerfile -t trampoline-vision:reid-study-05-frozen benchmarks/studies/05-reid

$reidDockerArgs = @(
  'run', '--rm', '--read-only', '--tmpfs', '/tmp',
  '--tmpfs', '/home/analyst/.cache:uid=1000,gid=1000',
  '--mount', "type=bind,source=${PWD}/benchmarks,target=/benchmarks,readonly",
  '--mount', "type=bind,source=${PWD}/../TFM,target=/workspace/TFM,readonly",
  '--mount', "type=bind,source=${PWD}/runs,target=/workspace/trampoline-vision/runs",
  'trampoline-vision:reid-study-05-frozen'
)
```

BoxMOT està fixat a la distribució 16.0.9, amb API NumPy compatible amb
aquest experiment. El log intern diu 16.0.8; s'utilitzen les metadades de
la distribució per comprovar-la. BoxMOT té llicència AGPL-3.0 i és una
dependència aïllada del benchmark. Els pesos són OSNet x0.25 entrenat a
MSMT17; l'estudi no els ajusta ni els reentrena.

Preparar els pesos i comprovar el port:

```powershell
docker @reidDockerArgs /benchmarks/studies/05-reid/prepare_weights.py --protocol /benchmarks/studies/05-reid/protocol.json --directory runs/reid-models
docker @reidDockerArgs /benchmarks/studies/05-reid/smoke_port.py --protocol /benchmarks/studies/05-reid/protocol.json --benchmarks /benchmarks --weights runs/reid-models/osnet_x0_25_msmt17.pt
```

## Execució nova i refinament amb cache

Una execució nova descodifica els tres clips i extreu els descriptors una
sola vegada. Es rebutja una carpeta de sortida existent.

```powershell
docker @reidDockerArgs /benchmarks/studies/05-reid/run_study.py --protocol /benchmarks/studies/05-reid/protocol.json --benchmarks /benchmarks --tfm /workspace/TFM --weights runs/reid-models/osnet_x0_25_msmt17.pt --output runs/tracking-reid-replay --threads 4
```

Per refinar només l'associació amb els descriptors ja generats, usar una
altra sortida i afegir `--reuse-embeddings-from`:

```powershell
docker @reidDockerArgs /benchmarks/studies/05-reid/run_study.py --protocol /benchmarks/studies/05-reid/protocol.json --benchmarks /benchmarks --tfm /workspace/TFM --weights runs/reid-models/osnet_x0_25_msmt17.pt --output runs/tracking-reid-refinement --threads 4 --reuse-embeddings-from runs/tracking-reid-study-05
```

Canviar una hipòtesi d'associació cada vegada en una còpia del protocol i
passar-la amb `--protocol`. El cache es rebutja si difereixen vídeo, CSV,
pesos, versions de preprocessament, ordre de candidats o descriptors.
Una modificació de preprocessament o del model exigeix extreure un cache nou.

## Avaluació i exportacions

```powershell
docker @reidDockerArgs /benchmarks/studies/05-reid/evaluate_study.py --runs runs/tracking-reid-replay --reference /benchmarks/studies/05-reid/review-reference.json --output runs/tracking-reid-replay/analysis.json
docker @reidDockerArgs /benchmarks/studies/05-reid/audit_recovery.py --runs runs/tracking-reid-replay --analysis runs/tracking-reid-replay/analysis.json --output runs/tracking-reid-replay/recovery-audit.json
docker @reidDockerArgs /benchmarks/studies/05-reid/render_comparison.py --runs runs/tracking-reid-replay --benchmarks /benchmarks --tfm /workspace/TFM --reference /benchmarks/studies/05-reid/review-reference.json --analysis runs/tracking-reid-replay/analysis.json
```

Si es conserva l'estudi 04, `evaluate_study.py` admet opcionalment
`--previous runs/tracking-yolo-study-04/ocsort_boxes.frames.jsonl` per exigir
igualtat exacta del baseline. La prova actual ja ha superat aquesta comprovació.

Les exportacions actuals definitives són a cada subcarpeta de cas de
`runs/tracking-reid-study-05/review-output-v2/`: vídeo comparatiu, tres
CSV de trajectòries i informe de verificació. L'ID ressaltat és una selecció
manual fixa per diagnòstic; no s'uneixen fragments ni es declara subjecte
automàtic. Els CSV distingeixen observat, predit i acabat. El centre de caixa
no és una articulació ni un centre de massa.

## Anotació i límits de la prova

`prepare_review.py --full-width` mostra tot el fotograma, perquè la posició
del panell negre canvia entre clips. `--left-panel-only` només és adequat
al cas conegut que té l'esport a l'esquerra i afecta únicament la làmina.
La lletra de revisió té alternatives per Windows i Linux.

La revisió inicial no mostrava trackers; la revisió 2 incorpora correccions
amb resultats ja visibles i conserva la versió anterior. Hi ha 178 mostres,
27 ambigües excloses i nou instants elegibles sense detecció del gimnasta.
No hi ha anotació densa independent de tot el vídeo. Els comptadors són
diagnòstics de pilot, no HOTA/MOTA/IDF1 ni garantia de continuïtat completa.

Vídeos, descriptors, pesos i cache no es versionen. Un `git pull` en un
altre equip aporta les eines i els resultats petits; cal aportar també les
entrades i, per evitar inferència, traslladar explícitament el cache local.
