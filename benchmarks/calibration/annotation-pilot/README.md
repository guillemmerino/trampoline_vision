# Mostra d'anotació visual provisional — v1, revisió 2

25/10/2026. Anotació visual del model d'OpenAI d'aquesta sessió, amb revisió
dels overlays pel mateix model. **Revisió humana pendent.** No és ground truth
independent ni s'ha registrat l'identificador exacte del model. No s'han fet
peticions addicionals a una API d'OpenAI.

## Mostra i procedència

| Vídeo | Motiu | Frames | Caixes | Ambigus/ocults |
| --- | --- | ---: | ---: | ---: |
| JPN_AGE_1_000905_31.0 | Històric, inversions i contacte amb assistent | 24 | 19 | 5 |
| JPN_AGE_2_000709_37.0 | Nou per al tracking, agrupacions, vol i rebot | 24 | 22 | 2 |
| JPN_AGE_3_001351_19.0 | Històric, inversions i assistent vermell al primer pla | 24 | 20 | 4 |
| Total | | 72 | 61 | 11 |

`selection.json` fixa àncores distribuïdes i finestres cada tres frames. AGE 1
aprofita intervals de fallada coneguts; AGE 2/3 s'han triat sobre mostres dels
originals. El model ja coneixia el context del projecte. És desenvolupament
exploratori, sense mostreig aleatori ni holdout independent.

Les caixes s'han proposat sobre originals i retalls amb regles externes, sense
dibuixos dels detectors o trackers. No s'han importat coordenades d'anotacions
antigues. Quan el retall inicial tallava el target, s'ha consultat el PNG complet.
Les caixes xyxy són en píxels originals i delimiten aproximadament el cos visible;
no reconstrueixen parts ocultes ni contenen una confiança numèrica inventada.

Hi ha deu casos `ambiguous` i un `occluded`, amb caixa null. El revisor humà
ha de validar també les exclusions: excloure instants difícils pot esbiaixar
la comparativa. Una caixa rectangular del gimnasta pot contenir píxels d'un
assistent superposat; l'IoU no demostra puresa d'identitat.

`corrections.json` conserva dues correccions de caixa als frames 445 i 448
d'AGE 1: després de dibuixar-les s'ha detectat que faltava part d'una cama/peu.
La revisió continua sent del mateix model, sense acreditació de precisió humana.

## Artefactes i reproducció

Els JSON petits de `references/` conserven status provisional, hashes de vídeo
i PNG, coordenades, exclusions, notes i procedència. Els originals i la galeria
són a `runs/annotation-pilot-v1/`, fora de Git:

- `raw/`: 72 PNG originals i làmines sense caixes.
- `review-v2/review.html`: original a l'esquerra i proposta a la dreta, clicables
  a mida completa. `review-v2/*/qa-*.jpg` mostra les caixes amb regles.
- `comparison/`: diagnòstic de traces històriques, sense repetir inferència.

Per validar en moviment, `runs/annotation-pilot-v1/videos/index.html` reuneix
tres MP4 dels vídeos complets amb 24 pauses cadascun i un MP4 dels 11 casos
exclosos. Els vídeos són H.264, amb fotograma complet i ampliació de detall.
Les caixes només apareixen als frames anotats; entre pauses hi ha context
sense anotació, no tracking continu ni caixes interpolades. El frame i temps
originals es mostren a la capçalera. Les pauses alteren el temps de reproducció
i el resum de dubtes mostra el context a un terç de velocitat.

Es poden regenerar en una carpeta nova des de la imatge de calibratge:

```bash
python -B benchmarks/calibration/render_annotation_videos.py --dataset /data --output /results/annotation-pilot-repeat/videos
```

La comprovació final valida còdec, geometria, recompte i timestamps dels MP4.
`videos/report.json` relaciona cada pausa amb el frame original i conserva
hashes dels vídeos i referències utilitzades. No modifica les anotacions.
Els MP4 són un afegit local posterior; no s'han afegit al ZIP congelat anterior.

`runs/annotation-pilot-v1.zip` empaqueta originals, revisió final, referències,
selecció i comparativa; té un `.sha256` al costat. És independent del paquet
original dels 94 vídeos/pesos, que es conserva intacte.

Per regenerar originals i galeria en carpetes noves:

```bash
python -B benchmarks/calibration/prepare_annotation_sample.py --output runs/annotation-pilot-repeat/raw
python -B benchmarks/calibration/review_annotation_sample.py --sample-root runs/annotation-pilot-repeat/raw --output runs/annotation-pilot-repeat/review
```

Aquests scripts extreuen i dibuixen. **No anoten vídeos nous amb una API.**
Les coordenades d'aquesta mostra són el resultat de la inspecció visual del
model en aquesta sessió. L'anotador massiu per API és un increment posterior.

## Ús exploratori al servidor

Les referències tenen `status: provisional` i `human_reviewed: false` i s'ometen
per defecte. Per utilitzar-les cal una opció explícita:

```bash
CALIBRATION_ANNOTATIONS="$PWD/benchmarks/calibration/annotation-pilot/references" \
bash benchmarks/calibration/run-server.sh \
  --suite pilot \
  --case JPN_AGE_1_000905_31.0 \
  --case JPN_AGE_2_000709_37.0 \
  --case JPN_AGE_3_001351_19.0 \
  --detector yolov8m-conf005-nms070 --tracker botsort-reid \
  --allow-provisional-references --output /results/annotation-pilot-v1
```

Són tres passades de detector i tres de tracking sobre els vídeos complets des
de zero. Els resultats són `evaluated_provisional_sparse`, amb procedència del
model i human_reviewed false. L'opció i els hashes entren a la identitat del run.
No es promocionen a `reviewed` ni es tria cap default.

## Reutilització de traces existents

Després de congelar les caixes corregides, s'han llegit les traces de l'estudi
05 d'AGE 1/3. S'ha comprovat el SHA de vídeo amb el corpus i les vinculacions
de l'estudi; SHA de traces i referències queden al resultat. No s'han reexecutat
detectors, trackers o descriptors. AGE 2 no tenia traça i queda pendent del
servidor. Els resultats petits són `exploratory-comparison.json` i `.csv`.

| Cas | Variant històrica | Matches observats | IDs als matches | Canvis entre matches |
| --- | --- | ---: | ---: | ---: |
| AGE 1, 000905 | OC-SORT | 16/19 | 7 | 8 |
| AGE 1, 000905 | BoT-SORT sense ReID | 16/19 | 6 | 6 |
| AGE 1, 000905 | BoT-SORT amb ReID | 16/19 | 4 | 3 |
| AGE 3, 001351 | OC-SORT | 14/20 | 4 | 3 |
| AGE 3, 001351 | BoT-SORT sense ReID | 14/20 | 4 | 3 |
| AGE 3, 001351 | BoT-SORT amb ReID | 14/20 | 5 | 4 |

IoU ≥ 0,5, matching de màxim IoU i només instants visibles d'aquesta mostra.
Són sensibles a duplicats, marges i selecció de frames. No són canvis exhaustius,
HOTA/IDF1/MOTA ni substitueixen l'estudi anterior, que tenia altres referències
i protocol. ReID no millora els canvis en aquesta mostra d'AGE 3; no es conclou
que una variant sigui millor globalment.

Per repetir amb els artefactes locals de l'estudi 05:

```bash
python -B benchmarks/calibration/compare_annotation_sample.py --output runs/annotation-comparison-repeat
```

El següent pas és revisar humanament caixes i exclusions, especialment peus,
mans, blur i contactes. Registrar correccions/revisor en una revisió nova abans
de marcar reviewed. La mostra comprova el procediment; encara no quantifica
la fiabilitat de l'anotador ni justifica una configuració final.
