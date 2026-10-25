# Estudi 03: geometria, evidència feble i diagnòstic

Experiments aïllats sobre el runtime 0.4.0, sense canvis als defaults ni
inferència nova. `explore.py` reutilitza la ingestió i la sessió de domini;
el port experimental ByteTrack usa només API pública de trackers 2.6.1.

## Reproduir

Des de l'arrel del projecte, amb el runtime 0.4.0 reconstruït i noms de
sortida nous. El directori d'experiment es munta només per a lectura:

```powershell
docker compose --profile tracking run --rm --volume ./benchmarks/cases/JPN_AGE_1_000905_31.0/study-03:/experiment:ro --entrypoint python tracking /experiment/explore.py --manifest data/manifests/JPN_AGE_1_000905_31.0.example.json --output-dir runs/study03-repeat --variants reference kp005 weighted byte_high byte_weak byte_weighted
docker compose --profile tracking run --rm --volume ./benchmarks/cases/JPN_AGE_1_000905_31.0/study-03:/experiment:ro --entrypoint python tracking /experiment/explore.py --manifest data/manifests/JPN_AGE_1_000905_31.0.example.json --output-dir runs/study03-strict-repeat --variants byte_strict
```

Els noms originals que espera `analyze.py` són `tracking-study-03` i
`tracking-study-03-strict`; per repetir l'anàlisi amb altres noms, adaptar
la selecció de carpetes o preservar una còpia del conjunt amb els noms
esperats. El programa rebutja sobrescriure una carpeta de resultat existent.

S'exporten fitxers separats per tram: 0–89 i 420–509. Les sessions processen
tots els fotogrames intermedis per escalfament i mantenen els temps originals.
El prefix ByteTrack s'explicita a l'exportació experimental; no s'ha afegit
un backend bytetrack a TrackerConfig de producció.

## Mesures i cauteles

`review-boxes.json` conté 25 caixes visuals aproximades: 13 del gimnasta i 12
de l'assistent. Es van inspeccionar sobre originals abans de consultar els
resultats d'aquests experiments. No tenen revisió independent i els marges
poden canviar IoU; no són anotacions esportives ni ground truth formal.

`analyze.py` reutilitza també les àncores de l'estudi 01, comprova que la
referència coincideix amb el baseline 0.4.0 i compara solapament a dos llindars.
L'assignació geomètrica és unívoca als actors revisats; les prediccions no
compten com a observacions. Els altres actors no estan anotats i no es pot
deduir precisió global ni falsos positius a partir del nombre de tracks.

`smoke_check()` demostra que mesures febles no inicien tracks sense llavor
forta, que poden mantenir-los i que la variant estricta exigeix ratxa de tres
mesures fortes per confirmar el naixement. La variant ByteTrack estàndard pot
acumular mesures febles després de la llavor forta; aquest matís es registra.

La poda ponderada usa els extrems observats als quantils de confiança 5–95%,
manté el score original i marca les caixes com a experimentals. No reescriu
articulacions ni pretén estimar les parts absents del cos.

Diagnòstic i resultats al [document 24](../../../../docs/24-final-geometry-and-weak-evidence-diagnosis.md).
