# 24. Diagnòstic de geometria i evidència feble

## Diagnòstic sobre aquest cas

El paquet 0.4.0 proporciona una infraestructura reproduïble i una confirmació
temporal corregida. **El recorregut actual amb OpenPose fusionat i caixes
derivades de punts encara no és prou fiable per alimentar salts o puntuació.**

L'estudi no justifica adoptar una poda genèrica de punts ni substituir OC-SORT
per ByteTrack sense més canvis. El problema és anterior i transversal:
**l'extensió dels punts visibles no equival a una caixa estable de persona**, i
les propostes poden ser parcials, tenir semàntica anatòmica errònia o barrejar actors.
La segona associació feble també pot prolongar una identitat sobre evidència
incorrecta si aquestes mesures són ambigües.

La recomanació és consolidar una mesura de persona independent i validable,
usar la pose com a evidència addicional i mantenir separats naixement fort,
associació feble, incertesa i articulacions absents. Això és una prioritat
arquitectònica a provar; no una garantia que un nou detector resolgui inversions.

## Què s'ha executat

Set variants sobre el mateix vídeo, sense entrenament ni inferència nova.
Cada sessió processa índexs 0–509 amb timestamps reals i exporta els mateixos
trams 0–89 i 420–509. Són 14 trams de resultat, amb escalfament compartit per
variant. Les primeres sis variants es processen juntes; la variant estricta
s'executa en una segona lectura. La referència coincideix exactament amb els
registres del baseline corregit, excloent run_id i l'etiqueta d'experiment.

| Variant | Geometria | Associació |
| --- | --- | --- |
| reference | Extensió original dels punts, política 0.4.0. | OC-SORT, score mínim 0.1. |
| kp005 | Seleccionar punts de confiança >=0.05. | Mateix OC-SORT. |
| weighted | Extrems 5–95% ponderats per confiança, mateix score original. | Mateix OC-SORT. |
| byte_high | Geometria original. | ByteTrack només amb caixes >=0.1. |
| byte_weak | Geometria original. | ByteTrack: altes >=0.1, baixes >=0.02; llavor de naixement >=0.1. |
| byte_weighted | Extensió ponderada. | Mateix ByteTrack amb associació feble. |
| byte_strict | Geometria original. | Associació feble només després de confirmar; naixement amb tres associacions fortes. |

Els experiments ByteTrack mantenen mínim intern 1, pressupost 0.5 s i IoU 0.1.
La confirmació de domini usa ratxa 3. En `byte_weak`, una llavor forta pot
acumular després associacions febles per completar la ratxa; `byte_strict`
impedeix això i reinicia la ratxa pendent si només hi ha evidència feble.

La implementació ByteTrack també usa un estimador d'estat diferent del
d'OC-SORT en aquesta biblioteca. Per aïllar l'efecte de l'evidència feble,
la comparació pertinent és byte_high/byte_weak/byte_strict, no atribuir totes
les diferències OC-SORT/ByteTrack únicament a la confiança.

## Comprovacions dels mecanismes

Amb una persona sintètica immòbil s'ha verificat:

- Una proposta 0.05, sola i sense llavor forta, no inicia una identitat ByteTrack.
- Una mesura 0.05 pot actualitzar una identitat existent iniciada amb mesures fortes.
- A la variant estricta, mesures febles intercalades no completen la confirmació.
- Després de tres associacions fortes consecutives, la mateixa identitat sí
  admet una nova mesura feble com a observació actual.

Això confirma que la separació fort/feble funciona com a mecanisme. No demostra
que les dades reals febles pertanyin a la persona correcta. Les proves són a
`smoke_check()` i el resultat es conserva a `runs/tracking-study-03/mechanism-checks.json`.

## Resultats amb les àncores fixes

S'han reutilitzat les 22 anotacions del primer estudi sense canviar-les segons
el resultat. Una àncora és una proposta concreta, no tota la persona; la
limitació de les propostes alternatives al fotograma 45 continua vigent.

| Variant | Àncores del gimnasta assignades, 14–17 s | IDs diferents en aquests matches |
| --- | --- | --- |
| reference | 5/6 | 3 |
| kp005 | 5/6 | 4 |
| weighted | 5/6 | 2 |
| byte_high | 5/6 | 5 |
| byte_weak | 3/6 | 3 |
| byte_weighted | 4/6 | 3 |
| byte_strict | 3/6 | 3 |

La variant weighted sembla millor si només es mira el nombre d'IDs de les
àncores. La revisió geomètrica següent mostra per què aquesta conclusió seria
precipitada. Igualment, menys IDs amb menys matches no prova més continuïtat.

Les confirmacions globals als dos trams passen de 194 a byte_high a 235 a
byte_weak; byte_strict les redueix a 199. El filtratge de naixements té efecte,
però la variant estricta encara no millora les àncores del gimnasta. Aquests
totals no són recomptes de falsos positius: falten anotacions de tots els actors.

## Revisió geomètrica addicional

S'han dibuixat aproximacions del volum visible de persona en 13 fotogrames
del gimnasta i 12 de l'assistent del fons, sobre imatges originals. No deriven
automàticament de les propostes i s'han fixat abans d'examinar aquestes sortides.
Són caixes pilot amb marges, revisades per l'assistent i sense validació
independent; no constitueixen ground truth formal ni avalen percentatges de
precisió per a tot el vídeo.

S'ha comparat IoU >=0.3 i >=0.5, amb assignació unívoca de caixes observades
als dos actors quan són revisables. No es compten prediccions com a mesures.
Les diferències sensibles al llindar o als marges es tracten com a diagnòstic,
no com a classificació validada dels algoritmes.

| Variant | Gimnasta: matches observats a IoU >=0.3 | A IoU >=0.5 |
| --- | --- | --- |
| reference | 7/13 | 4/13 |
| kp005 | 6/13 | 3/13 |
| weighted | 8/13 | 1/13 |
| byte_high | 7/13 | 3/13 |
| byte_weak | 5/13 | 2/13 |
| byte_weighted | 8/13 | 2/13 |
| byte_strict | 5/13 | 2/13 |

La referència té alguna caixa candidata amb IoU >=0.3 només en 8 dels 13
instants revisats, fins i tot abans de considerar identitat. Això assenyala
un límit de representació de les mesures, però no significa que el detector
no hagi vist cap part del gimnasta en els altres cinc instants: pot haver-hi
punts correctes amb una caixa massa estreta o un fragment.

Un exemple és el fotograma 420: una proposta coneguda del gimnasta té ID
correctament exportat, però la caixa de punts és molt estreta i no supera
IoU 0.3 amb la caixa aproximada del cos visible. Aquesta discrepància explica
per què no s'han de convertir aquests solapaments directament en precisió d'identitat.

## Què mostren les imatges

La placa `runs/tracking-study-03/geometry-review.jpg` compara la mateixa
proposta abans/després de ponderar; no substitueix propostes segons el tracker.

- **30:9:** l'amplada passa d'uns 14.85 a 5.13 píxels. La poda concentra la
  caixa sobre la línia d'articulacions, encara menys representativa del cos visible.
- **45:1:** s'elimina una part de l'extrem superior/esquerre, ocupada també
  per un braç realment estès. Retallar extrems no distingeix automàticament
  articulació errònia d'una extensió gimnàstica vàlida.
- **60:73:** s'elimina el punt llunyà i el rang Y es redueix d'aproximadament
  202–662 a 577–639. Hi ha una millora local contra l'outlier, però el resultat
  és un fragment de tronc, no una caixa de cos complet.
- **495:84:** la caixa canvia molt poc, mostrant que l'efecte depèn de com
  es distribueix la confiança en cada pose.

Per tant, la coherència geomètrica ha de descriure suport, parcialitat i
consistència, i no únicament produir rectangles més petits o més suaus.

## Diagnòstic i decisió

1. **Hi ha dos problemes diferents:** obtenir una regió de persona útil i
   mantenir-ne la identitat. En el cas actual també falla la primera part;
   no és just atribuir tota la fragmentació al tracker.
2. **L'evidència feble és útil només amb admissió i atribució fiables.** S'ha
   verificat el mecanisme i una variant estricta. Amb aquestes caixes no
   millora el gimnasta, de manera que no es promociona com a solució general.
3. **El següent experiment prioritari és separar detecció de persona i pose.**
   Provar un detector preentrenat que aporti caixes pròpies, amb adaptador i
   multirotació/crops verificats quan calgui. La pose aportaria articulacions
   i qualitat complementàries, sense obligar el tracker a interpretar cada
   esquelet parcial com el límit complet d'una persona. No cal entrenament propi
   per fer aquesta prova, però la capacitat sobre inversions s'ha de demostrar.
4. **L'acceptació necessita anotacions independents i un altre clip.** Prioritzar
   els instants de transferència entre gimnasta i assistent, casos negatius
   de persones properes i vídeo més nítid. Utilitzar identitat i regió visible,
   i conservar una part sense usar-la per triar llindars.
5. Amb mesures millors, comparar OC-SORT i una política de dues etapes amb
   naixements forts. Si continuen els canvis d'actor, estudiar moviment i
   aparença com a evidències addicionals, mesurant cost i fallades.

No es recomana començar el model puntuador ni afegir un predictor entrenat
per compensar silenciosament mesures incorrectes. La infraestructura queda
preparada per aquesta evolució, però el baseline encara ha de retornar
incertesa o manca d'evidència quan no pot sostenir identitat i articulacions.

## Abast i artefactes

No s'ha modificat el codi de producció, el registre de backends ni la
configuració per defecte. ByteTrack aquí és un port de benchmark aïllat,
no una nova opció executable del pipeline de producció.

Els scripts, caixes de revisió i protocol són a
[study-03](../benchmarks/cases/JPN_AGE_1_000905_31.0/study-03/README.md).
Resultats locals: `runs/tracking-study-03/` i `runs/tracking-study-03-strict/`.
El diagnòstic estructurat és `runs/tracking-study-03/analysis-final/diagnosis.json`.
No s'han reprocessat vídeos amb un model visual, descarregat pesos ni modificat TFM.

La justificació del mecanisme d'associació feble és a l'
[article original de ByteTrack](https://arxiv.org/abs/2110.06864). Les diferències
de l'API concreta s'han contrastat amb la wheel trackers 2.6.1, no assumit a
partir de la documentació de la versió latest.
