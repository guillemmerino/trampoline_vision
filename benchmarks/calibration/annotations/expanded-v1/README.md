# Mostra ampliada de localització: 18 vídeos

Estat: **referències preparades; la bateria de 36 inferències encara no executada**.
Objectiu: valorar la disponibilitat d’una caixa del gimnasta amb **0,001 principal
i 0,002 control**, mantenint la resta de paràmetres. No és una nova cerca de
llindars ni un estudi de continuïtat d’IDs.

## Abast congelat

18 vídeos complets, **17.340 fotogrames / 9 min 38 s**. S’anoten **80 fotogrames
per vídeo: 1.440 en total**, amb 1.267 caixes visibles i 173 estats ambigus/ocults
exclosos de la cobertura però presents a la galeria. Els 72 fotogrames antics
conserven coordenades i estat; hi ha 1.368 mostres addicionals.

| AGE | Desenvolupament (12) | Reserva temporal (6) |
| --- | --- | --- |
| 1 | `000840_34.0`, `000905_31.0`, `001814_34.0`, `002139_38.0` | `002837_43.0`, `005412_48.0` |
| 2 | `000024_27.0`, `000709_37.0`, `002952_23.0`, `003434_33.0` | `004622_33.0`, `005459_25.0` |
| 3 | `001122_32.0`, `001351_19.0`, `001618_22.0`, `002412_31.0` | `002828_43.0`, `003349_25.0` |

Els identificadors complets, SHA dels vídeos i fotogrames seleccionats són a
[selection.json](selection.json). S’ha substituït `JPN_AGE_2_001925_21.0` per
`JPN_AGE_2_002952_23.0`: als 12 instants de la làmina original del primer no s’hi
veia cap exercici; el segon sí que en mostra un. Això no és una anotació exhaustiva
d’absència al primer vídeo. El corpus i la suite `pilot` històrics no canvien:
el pla nou usa `suite=all` **amb una llista explícita de 18 casos**, i comprova
els límits de 18 vídeos / 36 detectors / 0 trackers abans d’executar.

## Mostreig i lectura dels resultats

Cada vídeo inclou 48 àncores uniformes entre el primer i l’últim fotograma.
S’hi afegeixen les mostres antigues, quan existeixen, i finestres amb separació
de 3 frames al voltant de dos instants escollits sobre imatges originals fins
a arribar a 80. Inclouen inversions, proximitat a assistents/aparell i algun
final de rutina; no tots els frames densos són necessàriament difícils.
No s’han consultat les sortides del detector per triar els nous instants.

La cobertura sobre `uniform` és el resum principal; `dense`, `legacy` i
`all_selected` són resums diagnòstics separats. Els estrats poden solapar-se i
no s’han de sumar. Cal informar també de les exclusions: es desconeix la
cobertura als frames exclosos i als no anotats. Les 1.440 mostres no són una
anotació exhaustiva dels 17.340 frames, ni permeten demostrar recuperacions
o continuïtat temporal.

Es comparen desenvolupament i reserva separadament. La reserva és temporal,
**de la mateixa competició/captura**, amb identitats d’esportistes desconegudes;
no és un holdout independent. La possible coincidència de temps dels noms
AGE1 `000840` i `000905` es manté al desenvolupament; els layouts diferents
impedeixen afirmar que hi hagi fotogrames duplicats només a partir del nom.
Després d’inspeccionar els resultats reservats, la reserva ja no és intacta.

## Procedència de les referències

L’usuari ha acceptat les bboxes d’IA com a referència d’aquest estudi. Tots els
fitxers mantenen **`status=provisional`, `reviewer_type=model`,
`human_reviewed=false`**: no s’afirma validació humana independent.

Les caixes noves parteixen de propostes per diferència amb el fons temporal
medià. El mateix agent ha inspeccionat les làmines originals amb les propostes
de tots els 1.440 frames i ha corregit moviment aliè, caixes d’aparell i membres
retallats. Ha consultat originals complets en casos laterals i ha fet comprovacions
puntuals dels dibuixos finals. La precisió dels límits és aproximada i no validada.
**No s’han fet servir les deteccions de YOLO per generar les noves caixes**, ni
interpolació, reconstrucció de membres ocults o recuperació d’IDs.

`provenance/` conserva les propostes, correccions visuals, recepta i manifest
d’extracció amb SHA de cada PNG. Les caixes antigues indiquen el SHA de la seva
referència pare. La captura local d’auditoria (originals, làmines i compilador)
és a `runs/calibration/sample-expansion-preparation-v1/`; no forma part de la
imatge Docker. Per extreure de nou els originals es pot usar
`prepare_annotation_sample.py --selection .../selection.json` amb un output nou.

[annotation-summary.json](annotation-summary.json) detalla caixes i exclusions
per vídeo. [localization-decisions-v1.json](localization-decisions-v1.json) accepta
les 18 referències per a l’estudi i hereta les quatre decisions explícites de
l’usuari sobre AGE2 f0 i AGE3 f180 a 0,001/0,002. Només es relliga el SHA de la
referència ampliada; la geometria d’aquests frames, els paràmetres i les
candidates exactes es conserven. No s’inventa parcialitat per als frames nous.

## Executar i revisar després

```bash
cd /home/tics/personal/trampoline-vision
bash benchmarks/calibration/commands/run-expanded-localization.sh
```

El wrapper construeix la imatge, comprova inputs i CUDA, congela el pla,
mostreig, referències i decisions, executa els 18 vídeos amb dos detectors i
genera `runs/calibration/expanded-localization-v1/REVIEW.md`.
La inferència veu el frame sencer: els crops només s’usen per revisar anotacions.
Es mantenen NMS 0,7, imgsz 1280, resize 1,5, FP32 i max_det 300; sense top20.
No hi ha trackers, ReID, recovery, prediccions temporals ni MP4. Es generen
1.440 làmines comparant les dues variants, incloses les exclusions.

Es registren temps del detector, RAM, VRAM, caixes totals i saturació de
`max_det`. El temps de generació de làmines es registra separadament; no hi ha
cache d’aparença. El paquet conté CSV complets, inputs congelats, checksums,
`review/summary.csv`, `review/samples.csv`, `review/grouped-coverage.csv` i
`review/index.html`, suficients per a una revisió posterior sense originals.

```bash
# Validació del pla i dels SHA, sense inferència:
bash benchmarks/calibration/commands/run-expanded-localization.sh --dry-run
# Continuar després d’una interrupció, sense canviar codi/inputs/configuració:
bash benchmarks/calibration/commands/run-expanded-localization.sh --resume
# Verificar/reconstruir la revisió sense GPU, models ni vídeos:
python3 -B -m benchmarks.calibration iterate \
  --output runs/calibration/expanded-localization-v1 --review-only
```

Prompt per a una conversa nova: «Revisa `runs/calibration/expanded-localization-v1/REVIEW.md`
i els checksums. Compara 0,001 principal i 0,002 control, separant desenvolupament,
reserva i àncores uniformes. Inspecciona casos recuperats, needs_review, parcials,
exclusions i saturació de max_det. Informa per vídeo i resum; conserva la
procedència d’IA. No canviïs paràmetres ni iniciïs més proves.»
