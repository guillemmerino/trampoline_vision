# Prototip de tracking per al trampolí

La mesura que més millora la continuïtat als clips reals és l’admissió de
caixes febles després de confirmar un ID. El model de vol provat no supera
la velocitat simple. Les simulacions mostren que la variant amb més
continuïtat als clips reals pot transferir un ID a un altre actor i
mantenir-l’hi durant molts fotogrames.

Per a una prova següent, prioritzar la **cerca geomètrica en dues passades
amb admissió feble selectiva i ReID opcional**. Comparar-la amb velocitat
simple amb admissió feble i amb el BoT-SORT enregistrat. La primera té el
millor compromís entre les variants provades quan hi ha contacte i
deformació simulats. La segona dona el millor resultat a les anotacions
disperses. Falta validar quina conserva millor l’actor en vídeo real.

## Disseny i entrades

El [pla executable](trampoline-tracker-prototype-v1.json) fixa 72 clips
sintètics (sis escenaris, 12 llavors, 180 fotogrames a 30 FPS), amb identitat
coneguda, i els tres vídeos complets del [contrast inicial](identity-continuity-v1.md).
Els escenaris aïllen salts nets, canvis de caixa, deteccions febles i
absents, contacte amb assistents, combinació de dificultats i un desplaçament
horitzontal sobtat de càmera. Els descriptors sintètics tenen un patró
propi per actor amb soroll i barreja en contactes. La seva capacitat de
discriminació depèn d’aquesta construcció i pot ser diferent de la d’OSNet.

El replay reutilitza els 2.610 fotogrames de candidates de YOLOv8m a 0,001,
zona central soft i màxim 12, els temps originals i els descriptors OSNet
del cache SQLite. Verifica el marcador original, les traces, el cache i
les referències. Les sortides enregistrades de BoT-SORT amb/sense ReID
fan de controls als clips reals. Les etiquetes d’actor només intervenen a
l’avaluació. No hi ha esquelets ni reunificació posterior.

Les variants comparteixen dues passades d’assignació amb possibilitat de
deixar el track sense candidata. Fan servir el centre i dimensions de caixa
separadament. La confirmació exigeix tres mesures fiables amb score de 0,10
i la retenció màxima és 0,5 s. Els llindars febles de prova són 0,02 i 0,001.

- **Cerca ampliada** cerca al voltant de l’última posició. És una aproximació
  pròpia inspirada en C-BIoU amb distància, IoU i un cost de mida compartit
  entre variants. [C-BIoU](https://arxiv.org/abs/2211.14317)
- **Kalman CV** estima centre i velocitat amb els temps reals. **Velocitat
  simple** combina desplaçaments recents. **Vol** afegeix acceleració
  vertical aproximada i més tolerància quan canvia el signe de la velocitat.
  Es dedueix el vol del moviment observat a la imatge, sense coordenades
  del llit, centre de massa ni simulació de l’impuls de rebot.
- **Protecció general** rebutja caixes que engloben centres de dos tracks
  confirmats o associacions amb alternatives de cost proper. **Admissió
  feble selectiva** reserva la comprovació estricta a scores inferiors a
  0,02. Exigeix una hipòtesi recent, una associació distingible i compatible
  i evita caixes cobertes per una mesura forta ja assignada.
- **ReID selectiu** desempata opcions geomètriques quan el descriptor
  discrimina. El descriptor es renova amb mesures fortes que no es
  consideren mixtes. **Retard de tres frames** puntua una continuació
  geomètrica de les dues opcions locals quan estan empatades. Té fins a
  100 ms de retard a 30 FPS i correspon a un desempat local.

La primera passada va comparar 13 variants. La segona va repetir aquestes
13 i va afegir set controls d’admissió feble sobre diferents predictors.
Els resultats sintètics de les variants repetides són idèntics. És una
exploració sobre els mateixos clips i llavors, sense conjunt de validació
independent.

## Resultats als tres vídeos reals

El parell compta com a continuïtat si el mateix ID apareix als dos extrems
anotats del gimnasta. El denominador és sempre 202. La cobertura mesura
observacions a les 179 anotacions amb candidata compatible (IoU ≥0,5).
Les associacions als extrems són geomètriques i les referències provisionals.

| Variant | Mateix ID / 202 | Observacions / 179 | Canvis amb observació als dos extrems | Mateix ID amb geometria permissiva / 202 |
| --- | ---: | ---: | ---: | ---: |
| BoT-SORT enregistrat | 109 | 149 | 10 | 113 |
| BoT-SORT + ReID enregistrat | 107 | 149 | 10 | 112 |
| Cerca ampliada | 98 | 150 | 20 | 105 |
| Kalman CV | 102 | 154 | 21 | 103 |
| Velocitat simple | 100 | 150 | 16 | 105 |
| Vol | 99 | 150 | 17 | 104 |
| Vol + admissió feble | 123 | 167 | 20 | 134 |
| Velocitat simple + admissió feble | 127 | 167 | 15 | 140 |
| Kalman CV + admissió feble selectiva | 124 | 168 | 19 | 130 |
| Cerca ampliada + admissió feble | 119 | 168 | 25 | 131 |
| Cerca ampliada + admissió feble selectiva | 116 | 163 | 20 | 127 |
| Cerca ampliada + admissió feble selectiva + ReID | 117 | 163 | 19 | 127 |
| Vol + protecció general | 57 | 99 | 7 | 59 |
| Vol + protecció general + retard de tres frames | 57 | 99 | 7 | 59 |

Velocitat amb admissió feble guanya 33 parells que BoT-SORT no mantenia i
en perd 15. Millora els totals a cadascun dels tres clips (43→49, 33→39
i 33→39), amb cinc canvis més entre extrems observats en el total. La variant
de cerca ampliada amb admissió selectiva i ReID guanya 26 parells i en
perd 18. El recompte d’extrems només cobreix els instants anotats.

Les caixes revisades a AGE2 #525, #527 i #531 exemplifiquen el mecanisme.
BoT-SORT no les observa. La velocitat amb admissió feble associa totes tres
i la cerca selectiva amb ReID n’associa dues. A AGE3 #97 les anotacions
continuen sense candidata útil preparada.

Com a comprovació addicional, s’han reutilitzat 15 fotogrames amb una
candidata explícitament etiquetada com a gimnasta en la revisió provisional
d’AGE1 i AGE3. S’hi detecten tres canvis de gimnasta a un altre actor en el
BoT-SORT enregistrat (13/15 fotogrames amb observació del gimnasta), un
en la velocitat amb admissió feble (12/15) i cap en la cerca selectiva amb
ReID (12/15). La mostra no permet estimar una taxa real de transferència.

## Simulació amb contacte, deformació i buits

Hi ha 1.848 fotogrames amb una candidata etiquetada com a gimnasta i 2.148
parells consecutius entre tots els clips de l’escenari combinat. Un canvi
d’actor es compta quan l’última observació amb rol clar d’un ID era el
gimnasta i l’ID passa a un altre actor. Les observacions contaminades
compten cada assignació d’un ID que ja havia seguit el gimnasta a un altre
actor o a una caixa mixta, també si l’assignació perdura diversos frames.

| Variant | Mateix ID / 2.148 | Observacions / 1.848 | Canvis d’actor | Observacions contaminades |
| --- | ---: | ---: | ---: | ---: |
| Cerca ampliada | 1.230 | 1.409 | 46 | 281 |
| Velocitat simple + admissió feble | 1.473 | 1.627 | 35 | 945 |
| Vol + admissió feble | 1.463 | 1.620 | 39 | 954 |
| Kalman CV + admissió feble selectiva | 1.387 | 1.546 | 29 | 370 |
| Cerca ampliada + admissió feble | 1.549 | 1.724 | 43 | 150 |
| Cerca ampliada + admissió feble selectiva | 1.494 | 1.656 | 44 | 148 |
| Cerca ampliada + admissió feble selectiva + ReID | 1.535 | 1.683 | 23 | 109 |

Amb el desplaçament sobtat de càmera, afegir ReID a la cerca selectiva
canvia les transferències de 51 a 26 i les observacions contaminades de
336 a 189. Entre els escenaris combinat i de càmera, redueix les
transferències en 22 de 24 clips simulats (un empat i una regressió).
Aquest efecte depèn dels descriptors simulats. Al replay amb descriptors
reals, afegir ReID canvia 116 a 117 parells i manté 163 observacions.

El model de vol es pot revisar quan disposem d’un indicador fiable de
contacte amb el llit o d’una mesura de posició menys sensible a la forma
de la caixa. La protecció general i el desempat de tres fotogrames en la
forma provada queden per darrere. Una decisió futura sobre el backend
hauria de mirar sobretot transferències als contactes en clips reservats
i cobertura de candidates febles, junt amb la continuïtat als extrems.

## Reproducció i traces

Des de l’arrel del repositori, amb la imatge local de calibratge i els dos
runs previs presents, executar la comanda amb un destí nou.

```bash
docker run --rm --network none --entrypoint python \
  --user "$(id -u):$(id -g)" \
  -e PYTHONPATH=/workspace/src:/workspace -e PYTHONDONTWRITEBYTECODE=1 \
  -e OPENBLAS_NUM_THREADS=1 \
  --mount "type=bind,src=$PWD,dst=/workspace,readonly" \
  --mount "type=bind,src=$PWD/runs/calibration,dst=/results" \
  -w /workspace trampoline-vision:calibration-gpu-v1 \
  -m benchmarks.calibration.tools.run_trampoline_tracker_prototype \
  --output /results/trampoline-tracker-prototype-repeat
```

La segona passada ha durat 71,3 s al contenidor i és a
`runs/calibration/trampoline-tracker-prototype-v1-followup/`.
`summary.json` conté els resultats per escenari i vídeo.
`simulated.jsonl.gz` conté mètriques per llavor.
`real-traces.jsonl.gz` conserva les assignacions i decisions per fotograma.
`real-pairs.jsonl.gz` conté el detall de cada parell en els dos criteris geomètrics.
`inputs.json` i `completed.json` vinculen fonts, codi, configuració i sortides.
La primera passada, amb menys variants, es conserva separada a
`runs/calibration/trampoline-tracker-prototype-v1/`.
