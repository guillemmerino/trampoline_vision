# Cas pilot: JPN_AGE_1_000905_31.0

Primera revisió del tracking 0.3.0, feta el 24/10/2026. S'han executat només
els intervals 0–3 s i 14–17 s amb el baseline, sense modificar llindars ni activar
deduplicació. Vídeo, ZIP i metadades originals continuen fora del repositori.

`annotations-baseline-01.json` i `annotations-flight-01.json` contenen 22
anotacions pilot: 10 del gimnasta i 12 de l'assistent situat darrere del trampolí.
S'han atribuït visualment per l'assistent sobre imatge original i propostes
individuals, sense revisió independent. No són anotacions d'exactitud articular,
no cobreixen tots els fotogrames i no constitueixen un benchmark formal.

Una anotació referencia una proposta concreta de la persona, encara que
sigui parcial. No afirma que tots els seus punts ni la seva caixa siguin correctes.
S'han omès casos amb atribució massa ambigua per barreja de persones, com els
fotogrames 60, 75 i 480 del gimnasta, conservant-los com a evidència qualitativa.

Limitació important: al fotograma 45 hi ha almenys dues propostes del gimnasta.
L'àncora `45:1` queda sense assignar, mentre `45:81` té `ocsort:61`.
Per tant, 0/4 àncores assignades al primer tram **no significa** que el tracker
no hagi observat mai el gimnasta. L'avaluador actual referencia una sola detecció
per subjecte/fotograma; una futura anotació amb alternatives o caixes independents
evitarà penalitzar una proposta correcta alternativa. No canviar les àncores en
funció del tracker que es vulgui afavorir.

## Reproducció

Les comandes de baseline i resultats són al
[document de revisió](../../../docs/22-first-tracking-baseline-review.md).
Les còpies dels JSON d'anotacions a `runs/tracking-review-01/` permeten usar
`evaluate-tracking` amb el muntatge habitual de Compose. Conservar els JSON
versionats com a referència i no sobreescriure resultats anteriors.

`confirmation_probe.py` és un cas sintètic separat de 10 fotogrames. Mostra que
amb `confirmation_frames=3`, després d'un buit, les dues primeres mesures de
recuperació es poden exportar com lost/predicted tot i existir detecció actual.
No llegeix estat privat ni modifica el codi o els paràmetres del baseline real.
Sortida guardada a `runs/tracking-review-01/confirmation-probe.json`.

El reproduïdor anterior descriu 0.3.0 i requereix el seu runtime històric:
les seves assercions ja no han de passar amb el paquet corregit. La regressió
0.4.0 és a `tests/integration/test_tracking.py`. La correcció i els experiments
posteriors són a [study-02](study-02/README.md) i al document 23.

L'estudi complet descriu aquesta limitació de la integració: els comptatges
lost/predicted no són una mesura directa de fotogrames sense detecció real.
