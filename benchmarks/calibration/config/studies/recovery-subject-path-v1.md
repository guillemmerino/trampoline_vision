# Prova del camí geomètric del gimnasta

El prototip geomètric **no recupera cap dels sis buits del catàleg** amb
una observació inicial comuna. A les 80 àncores verificades, selecciona
77 caixes d’altres actors i tres caixes que barregen el gimnasta i el
fons amb altres persones. La cobertura del graf és de 2.561 observacions
en 2.589 fotogrames després d’inicialitzar la identitat. La cobertura
mesura que el graf ha triat una caixa.

## Entrada i execució

El [pla](recovery-subject-path-v1.json) fixa les traces de
`velocity_soft_yolo`, el [catàleg](recovery-case-catalog-v1.md),
l’auditoria geomètrica anterior i els
[pesos de la simulació](recovery-subject-path-simulation-v1.md). Les
traces deriven de YOLOv8m a 0,001, amb preparació representativa, zona
central `soft` i 12 candidates als 2.610 fotogrames.

Les tres estratègies comencen a la mateixa caixa del gimnasta,
verificada visualment abans de la primera finestra de cada vídeo.
A AGE1 és el fotograma 8, ID 1. A AGE2 és el 10, ID 4. A AGE3 és el 3,
ID 0. Es llegeixen els vídeos complets i es reconstrueix des de cada
punt inicial fins al final, amb pas constant de 30 fps.

- El **tracker** segueix l’ID de la caixa inicial i deixa buits quan
  aquell ID deixa d’estar observat.
- L’**hongarès** segueix la cadena de l’auditoria existent que conté la
  caixa inicial.
- El **graf** considera totes les candidates i aplica els pesos de
  la simulació a centres en píxels i escala `sqrt(amplada * alçada)`.
  Els costos de moviment es normalitzen per l’escala de les caixes.
  Una candidata sense ID conserva un cost d’identitat neutre. El
  solver resol el mínim global amb memòria de les dues darreres caixes,
  amb salts de fins a cinc fotogrames intermedis i l’opció d’acabar
  deixant un buit. El marge és la diferència respecte al millor camí
  complet del vídeo. Els pesos s’han mantingut fixos.

## Avaluació

Per puntuar un parell, les dues caixes escollides han de ser útils
per al gimnasta segons la revisió, encara que portin IDs diferents.
El catàleg conté 80 fotogrames anotats, 63 dels quals tenen alguna
caixa útil identificada. Els 45 parells es formen entre àncores
successives del gimnasta dins d’una finestra. Cada buit catalogat
té un parell d’extrems explícit.

La [revisió visual complementària](../../reviews/recovery-case-catalog-v1/subject-path-v1-visual.json)
resol 104 caixes seleccionades que el catàleg original encara no
etiquetava. Les caixes es van comprovar sobre els píxels originals
i amb l’actor visible a la finestra. Tant el catàleg com les
etiquetes complementàries continuen provisionals, amb revisió
humana independent pendent.

| Mètode | Caixes útils del gimnasta / 80 | Altres actors | Caixes mixtes | Buits | Parells útils / 45 |
| --- | ---: | ---: | ---: | ---: | ---: |
| ID inicial del tracker | 1 | 15 | 0 | 64 | 0 |
| Cadena inicial de l’hongarès | 8 | 13 | 1 | 58 | 4 |
| Camí global del graf | 0 | 77 | 3 | 0 | 0 |

En cap dels sis buits els tres mètodes obtenen els dos extrems útils
des de la caixa inicial comuna. El **33/45** de
[l’auditoria anterior](recovery-geometry-v1.md) permetia comprovar
si els extrems compartien algun ID o cadena local, encara que la
cadena no contingués la caixa inicial del gimnasta.

## Diagnòstic

Les 63 àncores amb candidata útil són assolibles al graf. Forçar la
millor caixa útil en cadascuna augmentaria el cost del millor camí
complet almenys 0,334 punts, amb mediana 2,710. El llindar experimental
d’ambigüitat és 0,08. Sis àncores tenen alternatives dins del llindar,
i en totes sis les alternatives exclouen les caixes útils de referència.
A AGE2, als fotogrames 525 i 531, el graf tria públic a la graderia.
Forçar el 92 del gimnasta incrementa el cost 4,159 i 2,434 punts,
respectivament. La [làmina d’AGE2](../../reviews/recovery-case-catalog-v1/subject-path-v1-age2.jpg)
posa sis d’aquests fotogrames al costat de la seva caixa de referència.

El cost premia el desplaçament petit i la velocitat estable. Un
espectador o un jutge pot donar un camí llarg amb molt poc cost,
mentre que cada rebot o canvi de forma del gimnasta suma penalització.
Aquesta formulació necessita evidència del subjecte a cada tram.
Una comparació posterior pot mesurar per separat el suport de moviment
relatiu al fons o l’aparença del primer pla, amb el mateix protocol i
els mateixos vídeos de reserva.

## Reproducció

Des de l’arrel, amb la imatge local de calibratge, el corpus
`data/calibration-v1` i el run congelat `recovery-geometry-v1-reviewed`.
L’execució és en CPU i parteix de les caixes i els IDs enregistrats.

```bash
docker run --rm --network none --entrypoint python \
  --user "$(id -u):$(id -g)" \
  -e PYTHONPATH=/workspace/src:/workspace -e PYTHONDONTWRITEBYTECODE=1 \
  --mount "type=bind,src=$PWD,dst=/workspace,readonly" \
  --mount "type=bind,src=$PWD/runs/calibration,dst=/results" \
  -w /workspace trampoline-vision:calibration-gpu-v1 \
  -m benchmarks.calibration.tools.run_recovery_subject_path \
  --plan benchmarks/calibration/config/studies/recovery-subject-path-v1.json \
  --output /results/recovery-subject-path-v1-repeat
```

Les sortides verificades són a
`runs/calibration/recovery-subject-path-v1-reviewed/` (uns 15 MiB).
`summary.json` conté resultats i selectors per finestra. Cada
subdirectori té sis MP4 de quatre panells, la làmina de contrast i
el `path.jsonl` amb el camí i els marges de les alternatives a cada
fotograma. `completed.json` permet comprovar els 25 artefactes.
S’han comprovat 90 camins petits i 1.446 alternatives per enumeració
exhaustiva, i tres casos de regressió amb `unittest`.
