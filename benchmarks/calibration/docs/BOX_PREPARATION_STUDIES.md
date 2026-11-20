# Variants de preparació de caixes: models, resultats i pas a tracking

Aquest document consolida les simulacions espacials fetes sobre les mateixes
deteccions. Permet comparar models sense dependre de l’historial del xat.
El paquet implementa la preparació conservadora S0 i el perfil opcional de
12 caixes de la prova posterior. C i A/H es conserven com a comparadors
històrics. El perfil actual inclou les regles del model R, el rànquing per
silueta i la contenció protegida. Les mètriques històriques es mantenen
separades pels criteris i les mostres amb què es van calcular.

[Entrada del banc](../README.md) · [Estat de l’estudi](STATE.md) ·
[API de preparació implementada](../../../src/trampoline_vision/preparation/README.md).

## Continuació: llista curta a la zona del trampolí

S’ha repetit la comparació sobre les mateixes deteccions i les imatges reals.
La contenció encara deixava 112 candidats de mitjana per fotograma, en gran
part al públic i a la taula de jutges. En aquests plans de càmera fixa,
combinar zona del trampolí, regions febles, evidència de primer pla i una
salvaguarda de cobertura deixa **12 candidats actius**, amb 1.078/1.267
cobertures IA i 56/56 rectangles revisats. La prova amb vuit deixa 1.065
cobertures IA. Aquestes llistes encara inclouen distractors i regions massa
àmplies. El càlcul del fons usa mostres de tot el clip.

[Resultats, propostes i inspecció dels fotogrames](../../../runs/calibration/representative-box-study-v1/ASSESSMENT.md) ·
[Galeria comparativa](../../../runs/calibration/representative-box-study-v1/review.html).

## 1. Objectiu i límits comuns

L’objectiu és oferir al tracker menys hipòtesis redundants sense deixar de
localitzar el gimnasta. L’ID posterior ha de seguir la persona; la caixa pot
créixer, incorporar marge o incloure temporalment un assistent. Transferir
l’ID a l’assistent continua sent un error. La reconstrucció d’esquelets i
l’estudi de trajectòries articulars són fases posteriors.

Les famílies S0, C, A/H i R analitzen un sol fotograma. El perfil posterior
afegeix un fons fix calculat per clip. El tracking continu es mesura
separadament i la selecció automàtica del gimnasta és una fase diferent.

- Entrada: 1.440 fotogrames mostrejats de 18 vídeos, no els vídeos sencers.
  La inferència original sí que es va fer sobre els vídeos complets.
- Detector fixat: YOLOv8m, confiança 0,001, NMS 0,7, imgsz 1280,
  resize 1,5, max_det 300. Aquestes comparacions no recalculen YOLO.
- Fonts: 233.299 deteccions originals. S0 deixa 232.209 candidats,
  que són l’entrada comuna dels prototips següents.
- Revisió humana congelada r214: 56 seleccions útils de cinc vídeos AGE1,
  54 suficients i 2 parcials. Mostra dirigida, ja emprada per ajustar regles.
- Referències IA: 1.267 mostres visibles i 173 exclusions. Acceptades per
  l’usuari per a l’estudi, amb procedència provisional preservada; no són
  anotacions humanes exhaustives. No s’han usat per agrupar ni triar àncores.
- La reserva temporal original ja s’ha consultat; no és un test independent.
  Cap resultat d’aquí acredita comportament general als 94 vídeos.

### Què volen dir els nombres

Una **mostra** és un fotograma concret, no un vídeo. Els recomptes globals
sumen totes les candidatures de les 1.440 mostres, incloent públic i soroll.

El conjunt local és fix: 56 candidatures seleccionades més 137 alternatives
geomètriques, **193 en total**. Una alternativa és una altra caixa amb IoU≥0,5,
o una caixa petita amb IoS≥0,95 i àrea del 10–70% de la seleccionada.
No són 137 duplicats semàntics verificats: també hi ha assistents.
Es compten els grups de destí, per fotograma, d’aquest conjunt fix. Moure
una caixa fora de la zona no simula una reducció. Als prototips regionals,
les fonts en reserva ambigua no compten com a candidates actives; aquesta
reserva i la seva cobertura s’auditen per separat.

Per a una regió Q i una referència B:

- **Cobertura:** `àrea(Q ∩ B) / àrea(B)`; no és IoU.
- **IoS:** intersecció dividida per l’àrea de la caixa més petita.
- **Excés d’àrea:** `àrea(Q) / àrea(B)`, separat de la cobertura.
- **Caixa humana ≥95%:** disponibilitat d’una proposta que cobreix almenys
  el 95% del rectangle seleccionat. No vol dir que el tracker l’esculli.
- **IA ≥90%:** mostres amb alguna proposta que cobreix almenys el 90%
  del rectangle IA. S0 en té 1.054; amb àrea≤4×, 887.
- **Pèrdues:** casos que passaven un control amb S0 i deixen de passar-lo.
  No són necessàriament el saldo entre totals: pot haver-hi guanys nous.

A la galeria regional es destaca a posteriori la regió de menys àrea entre
les que passen cobertura≥95%; si cap no passa, la de màxima cobertura.
És una ajuda d’avaluació, **no un selector disponible en producció**.
A les simulacions anteriors també es segueix el grup propietari de la
selecció i de les alternatives; cal consultar la traça en comparar un cas.

La selecció humana pot ser ampla o parcial. No cobrir tot el seu marge no
prova que falti cos; cobrir-la amb una regió enorme tampoc prova una bona
localització. Els controls 90%, 95%, 4× i tots els llindars següents són
exploratoris, sense calibratge independent.

## 2. Diferències estructurals

| Família | Com decideix agrupar | Geometria resultant | Què protegeix o conserva actiu | Què no resol |
| --- | --- | --- | --- | --- |
| S0: conservadora implementada | Alternatives febles de mida i posició molt semblants, compatibles amb tots els membres | Una caixa observada del grup | Cobertura de cada font ≥95%; les contencions ambigües segueixen separades | Gairebé totes les parts internes continuen com a candidates |
| C: contenció | Un contenidor observat cobreix directament totes les fonts; ordre greedy | El contenidor observat | Límits de cobertura, àrea i confiança relativa segons variant | No protegeix totes les deteccions fortes com a àncores independents; pot agrupar actors diferents |
| A: àncores sense residuals | Àncores fortes ordenades per confiança/densitat; expansió amb suport addicional | Àncora o un contenidor observat | Cobertura de fonts; la resta queda separada | Moltes hipòtesis febles queden sense reduir |
| H: híbrid anterior | A, després C sobre el que queda lliure | Sempre caixa observada | Grups formats no es tornen a absorbir en cadena | La fase residual no és només feble; no hi ha protecció universal entre fortes ni regions derivades |
| R: àncores protegides i regió feble | Totes les fortes són àncores; assignació feble local; agrupació regional residual | Caixa observada per a fortes; extensió derivada per a regions febles | Fortes independents, febles aïllades i, en versió segura, extensió no explicada | Plausibilitat d’una sola persona, duplicats entre fortes i ambigüitat d’actor |

**Procedència i candidatura són coses diferents.** Tots els estudis preserven
les fonts amb caixes i scores originals. Però una font absorbida o en reserva
ja no és necessàriament una mesura independent accessible al tracker.
La conservació de metadades, tota sola, no garanteix conservar cobertura activa.

## 3. S0 — preparació conservadora implementada

`src/trampoline_vision/preparation/boxes.py`, activada explícitament amb
`configs/preparation/box-candidates.json`; desactivada per defecte als pipelines.

Agrupa des de la confiança més alta: score de l’alternativa≤25% de l’àncora,
IoU>0,65, semblança d’amplada i alçada≥0,8 i distància de centres per eix≤0,15
vegades la dimensió menor. Exigeix compatibilitat amb tots els membres.
El representant és la caixa observada de més àrea i ha de cobrir≥95% de cada
font. No fa unions, mitjanes ni expansions derivades. Les relacions de
contenció ambigües s’exporten, però no provoquen absorció.

Resultat: **233.299 → 232.209**, només 1.090 alternatives agrupades (0,47%).
En l’auditoria humana, les alternatives locals baixen de 138 originals a
137 preparades; cap de les 56 seleccionades agrupa altres fonts. Encara hi
ha solapaments o petites contingudes en 47/56 casos. És una base segura per
comparar, però insuficient per resoldre la redundància observada.

## 4. C — agrupament per contenció

No exigeix una confiança absoluta forta. Ordena contenidors per confiança
(o per menor àrea en `tight`) i absorbeix candidats lliures coberts directament.
Un singleton pot acabar absorbit per un contenidor posterior; un grup ja
format no es torna a absorbir en cadena. No deriva una caixa nova.

Els paràmetres codificats al nom són:

- `score095`/`090`/`098`: cobertura mínima de **cada font original**, no score YOLO.
- `area10`/`area4`: àrea del contenidor≤10×/4× l’àrea de **cada font** absorbida.
- `frame010`: una caixa de més del 10% de la imatge no absorbeix; es conserva sola.
- `conf025`: score del contenidor≥25% del score de **cada font** absorbida.
  És una relació, no un llindar absolut de detector.
- Sense `frame010`, no hi ha el límit del 10% de la imatge.

| ID exacte de variant | Globals | Locals /193 | Caixa humana ≥95% /56 | IA ≥90% /1.267 | IA ≥90% i àrea≤4× /1.267 | Pèrdues IA ≥90% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `current` | 232.209 | 193 | 56 | 1.054 | 887 | 0 |
| `score095_area10` | 144.792 | 89 | 56 | 1.052 | 767 | 2 |
| `score095_area4` | 148.439 | 108 | 56 | 1.052 | 825 | 2 |
| `score095_area10_frame010` | 147.743 | 90 | 56 | 1.054 | 852 | 0 |
| `tight095_area10_frame010` | 155.264 | 109 | 56 | 1.054 | 860 | 0 |
| `score090_area10_frame010` | 143.015 | 85 | 55 | 1.050 | 846 | 4 |
| `score098_area10_frame010` | 155.578 | 98 | 56 | 1.054 | 856 | 0 |
| `score095_area10_frame010_conf025` | 161.232 | 95 | 56 | 1.054 | 859 | 0 |
| `score098_area10_frame010_conf025` | 167.597 | 105 | 56 | 1.054 | 864 | 0 |

La referència de contenció és **`score095_area10_frame010_conf025`**:
95 candidats locals i 161.232 globals; 56/56 cobertures humanes; cap pèrdua
IA≥90%. El control d’àrea passa de 887 a 859 mostres. Només quatre caixes
humanes superen 2× d’àrea. El màxim observat **3,75× no és un límit imposat**:
el límit és 10× respecte de cada font i 10% de la imatge.

La confiança relativa evita alguns contenidors molt febles i enormes.
Exigir cobertura 98% deixa més candidats (105 locals) i conserva més regions
ajustades (864). Baixar-la a 90% redueix més (85), però perd quatre cobertures
IA anteriors. Per tant, minimitzar recompte no basta per escollir variant.

## 5. A/H — àncora, densitat, expansió observada i residuals

L’àncora és la font més confiada d’una candidata, score≥0,1 (control 0,05).
La densitat compta altres candidates amb IoS≥0,5 i relació d’àrees 0,1–10.
Són propostes correlacionades del detector, no persones ni evidència independent.
No s’utilitza una mida global de persones del públic, que barrejaria profunditats.

`anchor_confidence` ordena per score; `anchor_density` exigeix≥3 veïnes i
ordena per densitat; `anchor_balanced` usa `sqrt(score) × log(2 + densitat)`.
`hybrid_gated_balanced` afegeix≥3 veïnes a l’ordre equilibrat.

L’expansió selecciona **un contenidor observat** que cobreixi≥95% de les fonts,
amb àrea≤4× l’àncora inicial i≤10% del fotograma. Es valora el suport veí
addicional explicat: suma de `sqrt(score)` menys `0,1 × log(àrea nova / inicial)`.
La caixa proposada no vota per justificar-se ella mateixa. No s’expandeix en cadena.
La confiança de l’àncora i la de la caixa que aporta la regió es conserven separades.

Les variants `hybrid_*` apliquen després la contenció C de referència als
candidats encara lliures. **No és una fase exclusivament feble:** pot incloure
fortes aïllades. Les fortes sense suport dens es conserven, però no tenen el
tractament d’àncora protegida del model R. Una forta pot ser absorbida per un
altre grup; cap regla universal ho prohibeix en aquesta família.

| ID exacte de variant | Globals | Locals /193 | Caixa humana ≥95% /56 | IA ≥90% /1.267 | IA ≥90% i àrea≤4× /1.267 | Pèrdues IA ≥90% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `current` | 232.209 | 193 | 56 | 1.054 | 887 | 0 |
| `containment_reference` | 161.232 | 95 | 56 | 1.054 | 859 | 0 |
| `anchor_confidence` | 210.509 | 88 | 56 | 1.054 | 883 | 0 |
| `anchor_density` | 217.217 | 93 | 56 | 1.054 | 883 | 0 |
| `anchor_balanced` | 210.445 | 88 | 56 | 1.054 | 883 | 0 |
| `hybrid_confidence` | 156.779 | 82 | 56 | 1.054 | 863 | 0 |
| `hybrid_density` | 157.295 | 82 | 56 | 1.054 | 862 | 0 |
| `hybrid_balanced` | 156.726 | 82 | 56 | 1.054 | 862 | 0 |
| `hybrid_balanced_x8` | 154.650 | 75 | 56 | 1.054 | 819 | 0 |
| `hybrid_lowseed` | 155.576 | 82 | 56 | 1.054 | 862 | 0 |
| `hybrid_auxouter` | 150.918 | 75 | 56 | 1.050 | 844 | 4 |
| `hybrid_gated_balanced` | 157.300 | 82 | 56 | 1.054 | 862 | 0 |

`hybrid_confidence`, `hybrid_density` i `hybrid_balanced` canvien l’ordre;
`hybrid_balanced_x8` només amplia el límit a 8×;
`hybrid_lowseed` baixa el score fort a 0,05;
`hybrid_auxouter` permet arxivar contenidors febles sense explicar-ne tot el marge;
`hybrid_gated_balanced` exigeix densitat mínima a l’ordre equilibrat.

La referència H és **`hybrid_gated_balanced`**: 82 locals, 157.300 globals,
56/56 cobertures humanes i cap pèrdua IA≥90%. Millora la reducció respecte de
C (95→82), però els casos humans amb regió>2× passen de 4 a 11. La disponibilitat
IA amb àrea≤4× és 862 davant de 859: això no elimina els casos individuals
visiblement massa amplis. El control 8× redueix fins a 75 locals, amb pitjor
cost d’àrea (819). Arxivar marges també dóna 75 locals, però perd quatre
cobertures IA: conservar procedència no ha evitat aquesta pèrdua activa.

## 6. R — totes les fortes protegides i regions febles derivades

Aquest model incorpora la clarificació posterior: una forta és una àncora
encara que estigui sola; les febles suggereixen expansió; una zona feble densa
sense assignació clara pot ser **una única candidata regional provisional**.
No és equivalent a H amb uns altres llindars.

### Regles comunes

1. Totes les candidates amb font de score≥0,1 es conserven com a àncores
   fortes. Dues fortes no s’absorbeixen. Poden solapar-se realment; el prototip
   no resol encara si dues fortes gairebé coincidents són duplicats.
2. Cada feble compatible es vincula pel millor encaix:
   `IoU + 0,5 × intersecció/àrea feble + 0,1 × intersecció/àrea àncora`.
   Veïnat: IoS≥0,5, relació d’àrees 0,1–10. Si dos encaixos difereixen<0,1,
   l’assignació és ambigua; no es resol només amb el score màxim.
3. L’expansió de la forta usa una caixa feble observada vinculada i suport
   addicional, amb la penalització d’àrea anterior. El límit és 1,5× per
   score≥0,5 i 3× per score 0,1–0,5, respecte de l’àncora inicial. No redueix una
   regió d’entrada que ja superi el límit: el pressupost és el màxim entre
   l’àrea inicial heretada i el límit calculat. Propostes d’expansió≤10% d’imatge.
4. Una expansió no pot passar de cobrir<50% a≥50% d’una altra àncora forta.
   Això frena noves absorcions geomètriques; no separa actors que ja se solapen.
5. Entre les febles lliures, la llavor amb més veïnes, amb score com a desempat,
   proposa un grup. S’afegeixen veïnes directes ordenades per IoU i score,
   construint el rectangle que les engloba. Calen≥4 candidates; àrea≤6× la
   llavor i≤10% d’imatge. La llavor és fixa; no hi ha propagació en cadena.
6. La regió substitueix les seves candidatures constituents. Les febles
   aïllades continuen com a candidates provisionals: no s’esborren per manca
   de suport fort o densitat.

La protecció entre fortes no valida semànticament una regió feble: aquesta
pot incloure altres persones o solapar àncores que continuen separades.

La regió feble és **`support_extent`**, geometria espacial derivada, amb
`region_score=None`; conserva scores originals i score de llavor per separat.
No s’inventa una confiança YOLO per a la unió ni és una predicció temporal.

### Què canvia cada control

| Variant | Límits forta molt confiada / altra forta | Regió feble | Fonts febles fora de la regió forta | Assignació ambigua |
| --- | --- | --- | --- | --- |
| `tiered_strict` | 1,5× /3× | Sí, límit 6× | Es poden absorbir sense cobrir-ne tot el marge | Reserva d’evidència, sense candidata activa |
| `tiered_keep_outer` | 1,5× /3× | Sí, 6× | Tornen a residuals si alguna font queda coberta<50% | Reserva d’evidència |
| `tiered_relaxed` | 2× /4× | Sí, 8× | Com l’estricte | Reserva d’evidència |
| `uniform_growth4` | 4× /4× | Sí, 6× | Com l’estricte | Reserva d’evidència |
| `tiered_no_regional` | 1,5× /3× | No; residuals individuals | Com l’estricte | Reserva d’evidència |
| `tiered_safe_regional` | 1,5× /3× | Sí, 6× | Tornen a residuals si alguna font queda coberta<95% | Torna a regions febles o singleton |

La versió segura **no força una expansió** per explicar qualsevol marge:
retorna el suport no explicat al procés regional o el conserva individualment.
Totes les variants conserven les fonts, però només aquesta retorna també les
ambigües com a hipòtesis actives. Les altres reserven 995 candidates d’entrada
com a evidència ambigua al conjunt global; això també redueix el recompte actiu.

| ID exacte de variant | Globals | Locals /193 | Caixa humana ≥95% /56 | IA ≥90% /1.267 | IA ≥90% i àrea≤4× /1.267 | Pèrdues IA ≥90% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `current` | 232.209 | 193 | 56 | 1.054 | 887 | 0 |
| `previous_hybrid` | 157.300 | 82 | 56 | 1.054 | 862 | 0 |
| `tiered_strict` | 150.976 | 69 | 53 | 749 | 523 | 309 |
| `tiered_keep_outer` | 158.050 | 73 | 55 | 1.047 | 809 | 17 |
| `tiered_relaxed` | 150.707 | 68 | 53 | 753 | 527 | 306 |
| `uniform_growth4` | 150.976 | 69 | 53 | 755 | 531 | 303 |
| `tiered_no_regional` | 194.504 | 77 | 53 | 744 | 537 | 310 |
| `tiered_safe_regional` | 164.772 | 89 | 56 | 1.079 | 817 | 0 |

`previous_hybrid` reprodueix exactament H (`hybrid_gated_balanced`);
`current` és S0 en les tres taules. No són experiments diferents.

L’estricte aconsegueix 69 locals, però perd 309 cobertures IA anteriors i només
cobreix 53/56 rectangles humans. Tres discrepàncies rectangulars no equivalen
a tres gimnastes absents: hi ha marges excessius, però també un cas inspeccionat
amb cos fora de la regió. Relaxar els límits d’expansió no resol aquesta pèrdua:
el problema també és absorbir suport no explicat i reservar ambigüitats.

**`tiered_safe_regional` és el control R compatible amb prioritzar cobertura**:
89 locals, 164.772 globals, 56/56 cobertures humanes i zero pèrdues de les
1.054 cobertures IA anteriors. Genera 12.169 regions febles i protegeix 36.086
àncores fortes; manté 116.517 singletons febles i no deixa fonts en reserva.

Les 1.079 cobertures IA inclouen 25 guanys geomètrics: no són 25 persones noves
verificades. El control d’àrea baixa a 817: perd 92 casos anteriors i en guanya 22
(`887 − 92 + 22 = 817`). No s’ha d’interpretar la diferència neta de 70 com si
fos el recompte de pèrdues. En nou casos humans la regió supera 2× d’àrea.

## 7. Comparació principal i explicació de les diferències

| Model de referència | Globals | Locals | Humana≥95% | IA≥90% | IA≥90%, àrea≤4× | Casos humans d’àrea>2× |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| S0: conservadora | 232.209 | 193 | 56/56 | 1.054 | 887 | 0 |
| C: contenció 95% amb salvaguardes | 161.232 | 95 | 56/56 | 1.054 | 859 | 4 |
| H: densitat + confiança + residuals | 157.300 | 82 | 56/56 | 1.054 | 862 | 11 |
| R: fortes protegides + regional segura | 164.772 | 89 | 56/56 | 1.079 | 817 | 9 |

**C és la referència més simple:** redueix molt respecte de S0 sense fabricar
regions, però pot escollir contenidors febles d’altres actors. H redueix més
al voltant de les seleccions, perquè agrupa amb àncores i tracta residuals;
no garanteix protegir un assistent com una persona independent.

**R expressa millor el model acordat**, separant fortes, suport feble i regions
provisionals. Respecte de C baixa només 95→89 locals (−6,3%), mentre que els
globals pugen 161.232→164.772 (+2,2%). Respecte de H deixa set locals més.
Això pot ser un cost útil de protegir persones diferents, no només redundància
que l’algoritme no hagi eliminat. Les unions regionals també poden créixer
massa: R no domina C/H en recompte ni en cost d’àrea.

### Casos concrets, per poder revisar el motiu

Els IDs abreujats següents són de `JPN_AGE_1`; el número després de dos punts
és l’índex de fotograma. Són lectures visuals de l’agent, sense nous veredictes humans.

| Vídeo / frame | Diferència observada | Què ensenya |
| --- | --- | --- |
| `000840_34.0:889` | H deixa 6 locals; R estricte 2 però només 24% de cobertura del rectangle; R segur 3 amb regió feble de 10 candidates i àrea 1,15× | La densitat feble pot reconstruir una regió útil quan una forta parcial no explica el cos |
| `000840_34.0:753` | R estricte cobreix 67% del rectangle, però sembla una caixa corporal més ajustada | La cobertura d’un rectangle ample pot penalitzar una bona caixa; cal revisió corporal |
| `002837_43.0:686` | R segur cobreix el rectangle amb una regió 5,17× que inclou assistent/fons | Preservar tot el marge pot fabricar una regió menys útil |
| `002837_43.0:718` | H: 3 locals→R: 1 regional; encara inclou molt fons | Densitat i reducció no certifiquen plausibilitat d’una sola persona |
| `002139_38.0:645` | C/H encara fan una regió ampla; R agrupa 2→1 però continua amb jutges/fons | La regió derivada no resol semànticament el problema del contenidor |
| `000905_31.0:720` | C/H: 1 local→R: 2: gimnasta i assistenta separats | Menys candidats no sempre és millor: abans s’absorbia una altra persona |
| `002837_43.0:709` | C/H deixen 2 locals, però H amplia fins a 3,32× sense guany de recompte | Una expansió que explica soroll pot tenir cost sense benefici observable |

La confiança de YOLO valora la hipòtesi de persona, **no cos complet ni identitat**.
Entre les 56 seleccions, 40 tenen score≥0,1 i 10<0,01; la mediana és 0,394.
Les petites contingudes i solapades acostumen a ser menys confiades, però
hi ha excepcions fortes: una detecció de cap/tronc pot tenir score alt.
Per això «més confiança→menys expansió» és una hipòtesi, no una llei validada.
La densitat també pot venir de cartells, públic i propostes correlacionades.

## 8. Rendiment computacional: què s’ha mesurat

| Execució | Treball mesurat | Temps de paret en CPU registrat | Interpretació |
| --- | --- | --- | --- |
| S0 `box-preparation-v3` | 1 política sobre 1.440 fotogrames, Python 3.12 | 14,35 s de preparació; 19,20 s total | Mitjana 9,97 ms/frame, p95 13,24 ms; inclou càlcul de relacions en la preparació |
| C `containment-grouping-simulation-v1` | 9 comparacions, NumPy i geometria compartida | 22,10 s total | Lectura, càlcul, diagnòstics i exportació del prototip |
| A/H `density-anchor-simulation-v1` | 12 comparacions, NumPy i geometria compartida | 24,04 s total | Mateixa naturalesa; no és temps per vídeo ni per tracker |
| R `tiered-anchor-regions-v1` | 8 comparacions, NumPy i exportació | 55,16 s total | Inclou exportar traces; compressió i galeria es fan separadament |

Els totals dels prototips són els cronòmetres de `result.json`, no una mesura
completa de tots els scripts de validació/renderització. Els cronòmetres per
variant exclouen feina compartida: no serveixen per proclamar un guany de
velocitat respecte de S0. No s’han repetit execucions per estimar variabilitat.

**Cap temps d’aquesta taula inclou generar MP4**: no se n’han generat en
les simulacions. No hi ha inferència, GPU ni cache de descriptors; es
reutilitzen deteccions desades. VRAM de models/tracking no s’ha mesurat.
S0 registra RSS màxim 421,3 MiB, incloent carregar tot el bundle, no memòria
incremental de l’algoritme. Els prototips C/A/H/R no registren RAM màxima:
no hi ha una comparació de memòria disponible. Reduir candidats podria
abaratir associació o aparença, però aquest guany encara **no s’ha mesurat**.

## 9. Protocol històric proposat abans del replay continu

Aquest era el protocol proposat abans d’executar la prova contínua. La matriu
que es va executar després es descriu a l’apartat 14.
La comparació mínima útil és: **deteccions sense agrupar, S0, C de referència,
H de referència i R segur**, sobre les mateixes deteccions i trams continus.
Les variants estrictes/agressives queden com a controls de risc, no com a
candidats preferents només pel recompte.

1. Fixar detector, vídeos, tracker, llindars d’associació/confirmació/retenció
   i context inicial; canviar només preparació. Primer aïllar-ne l’efecte
   amb el mateix tracker i sense recuperació externa d’IDs.
2. Adaptar C/H/R al flux de preparació de **tots** els fotogrames dels clips
   seleccionats. El bundle de 1.440 mostres no és un stream continu per fer
   tracking. Les assignacions exportades són traces d’auditoria, no un
   input ja compatible amb `TrackingSession`.
3. Exportar origen observat/derivat, àncora, regió, fonts, scores originals,
   ambigüitats i política efectiva. El protocol proposava representar
   `support_extent` explícitament. El perfil implementat afegeix aquest
   origen a `BoxMeasurement` i usa el score original de la llavor amb
   mètode declarat.
4. Conservar auditoria completa de preparació: el JSONL compacte de tracking
   actual no conté totes les geometries de les fonts agrupades ni les
   relacions noves. Desar configuracions i hashes per reproduir la prova.
5. Avaluar localització observada, durada de pèrdues, fragmentació i canvis
   d’ID, identitats duplicades i transferències a assistents. Separar
   **observacions del detector**, **regions espacials derivades** i
   **prediccions temporals del tracker**. Un frame predit no és una detecció.
6. Revisar finestres contínues anotades al voltant de girs, oclusions,
   contactes amb assistents, expansió/contracció i reentrada. Les 56 seleccions
   actuals ajuden a escollir casos; no permeten mesurar exhaustivament IDF1,
   HOTA o estabilitat de tot el vídeo. Incorporar AGE2/AGE3 i dades noves
   sense ajustar-les abans de la comparació final.
7. Generar overlays amb àncora, ROI i ID; registrar temps de detector,
   preparació, associació, exportació i MP4 separadament, més total amb vídeo,
   RAM, VRAM i hits/misses del cache. Comparar qualitat i recursos per clip
   i variant, amb el mateix criteri de selecció inicial del gimnasta.

La hipòtesi proposada era que una reducció de redundància amb cobertura
preservada faciliti una identitat estable. No es dóna per provada: una regió
més gran pot empitjorar geometria, aparença i separació entre actors.
La comparació detallada de C/H/R amb tracking queda com a proposta històrica.

## 10. Controls inicials de supressió: criteri històric

Abans de S0 es van provar aquestes variants sobre les 233.299 caixes raw.
La columna IA usa **IoU≥0,5**, i la humana exigeix conservar **exactament** la
caixa escollida. No són les mètriques de cobertura 90/95% de les taules anteriors.
NMS es reaplica després del NMS0,7 original; no equival a repetir YOLO amb un
altre NMS. Cap d’aquests controls es va convertir en un nou default.

| Control inicial | Candidats globals | IA IoU≥0,5 /1.267 | Selecció humana exacta /56 |
| --- | ---: | ---: | ---: |
| Raw original | 233.299 | 1.204 | 56 |
| NMS IoU0,50 | 153.269 | 1.168 | 44 |
| NMS IoU0,60 | 178.566 | 1.187 | 51 |
| NMS IoU0,65 | 198.509 | 1.195 | 52 |
| Supressió IoS≥0,90 sense salvaguardes | 125.214 | 1.034 | 41 |
| IoU>0,65 o contenció condicionada | 170.456 | 1.190 | 50 |
| Només contenció condicionada | 195.759 | 1.197 | 54 |
| Similitud estricta inicial | 232.745 | 1.204 | 56 |

Contenció condicionada: IoS≥0,95, àrea petita/gran 0,1–0,7 i confiança
petita≤0,25× confiança gran. La similitud inicial també imposava semblança
d’àrea≥0,8; **no és la política S0 final**, que afegeix salvaguarda de
cobertura del representant i controla semblança d’amplada/alçada sense aquest
límit d’àrea addicional. Per això 554 agrupaments inicials i 1.090 a S0 no són
una contradicció. Les revisions intermèdies v1/v2 del desenvolupament no són
variants candidates per a tracking; la base congelada és v3.

Aquests controls van mostrar que suprimir agressivament per solapament pot
apartar caixes útils o afavorir assistents i contenidors de fons. Soft-NMS i
Weighted Boxes Fusion es van discutir com a alternatives, però **no s’han
simulat** ni tenen resultats propis en aquest estudi.

## 11. Evidència, reproducció i accés a les galeries

| Estudi local a `runs/calibration/` | Evidència principal |
| --- | --- |
| [`box-preparation-feasibility-v1`](../../../runs/calibration/box-preparation-feasibility-v1/ASSESSMENT.md) | Controls inicials NMS/contenció; criteri històric IoU, no comparable directament a cobertura 90/95% |
| [`box-preparation-v3`](../../../runs/calibration/box-preparation-v3/INTERPRETATION.md) | Implementació S0, `frames.jsonl`, config, temps i fonts completes |
| [`human-approved-redundancy-v1`](../../../runs/calibration/human-approved-redundancy-v1/ASSESSMENT.md) | Conjunt local fix i auditoria de les 56 seleccions |
| [`containment-grouping-simulation-v1`](../../../runs/calibration/containment-grouping-simulation-v1/ASSESSMENT.md) | C: `simulate.py`, `result.json`, `assignments.json`, [galeria](../../../runs/calibration/containment-grouping-simulation-v1/review.html) |
| [`confidence-anchor-analysis-v1`](../../../runs/calibration/confidence-anchor-analysis-v1/ASSESSMENT.md) | Scores seleccionats, continguts, contenidors i solapaments |
| [`density-anchor-simulation-v1`](../../../runs/calibration/density-anchor-simulation-v1/ASSESSMENT.md) | A/H: `study.py`, `result.json`, `assignments.json`, `anchor-ranking.json`, [galeria](../../../runs/calibration/density-anchor-simulation-v1/review.html) |
| [`tiered-anchor-regions-v1`](../../../runs/calibration/tiered-anchor-regions-v1/ASSESSMENT.md) | R: `study.py`, `result.json`, `assignments.jsonl.gz`, `human-views.json`, [galeria](../../../runs/calibration/tiered-anchor-regions-v1/review.html) |

Els estudis C/A/H/R tenen instantànies, hashes d’entrada, `validation.json`
i `checksums.json`; es van comprovar totes les particions de 233.299 fonts
per variant i 4/6/7 casos sintètics respectivament. R audita també protecció
de fortes i límits regionals. Aquestes verificacions acrediten les regles
implementades, no identitat semàntica correcta ni un òptim general.
S0 té comprovacions unitàries/integració; detall als artefactes del seu run.

L’arxiu d’evidència de l’apartat 12 conserva els resultats principals i les
imatges representatives amb hashes. Els scripts experimentals originals,
les traces completes i la revisió humana viva continuen sota `runs/`.
Per reproduir totes les variants històriques exactament, cal conservar
aquells runs i les entrades congelades. R importa A/H i aquests reutilitzen C.
El benchmark continu prova el mètode seleccionat i variants de tall i zona.

Comanda **existent**, només S0 i sense tracking; triar sempre output nou:

```bash
PYTHONPATH=src python3 -m benchmarks.calibration prepare-boxes \
  --bundle runs/calibration/expanded-localization-v1/human-review/bundle.json \
  --config configs/preparation/box-candidates.json \
  --decisions runs/calibration/expanded-localization-v1/human-review/review-state.json \
  --output runs/calibration/box-preparation-review-v1
```

Usa l’estat humà vigent, que pot ser posterior a r214. Per reproduir les
xifres d’aquest document cal l’instantània r214 del run, no una revisió viva
que hagi canviat. Cap d’aquestes comandes converteix S0 en C/H/R.

Per veure les galeries al navegador, des de l’arrel del projecte:

```bash
python3 -m http.server 8767 --bind 127.0.0.1 --directory runs/calibration
```

Reenviar 8767 si es treballa per SSH. Obrir
`http://localhost:8767/tiered-anchor-regions-v1/review.html`, o canviar el
nom del run per veure C/H. Cal servir tota l’arrel `runs/calibration` perquè
els HTML referencien imatges de l’entrada en carpetes germanes.
Aquest servidor és de lectura; la revisió humana amb desament continua
separada a 8766. No s’han modificat aprovacions per redactar aquest document.

### Empremtes dels resums utilitzats

Les taules anteriors transcriuen `statistics` dels JSON següents; les
empremtes permeten detectar si es consulta una altra versió dels resultats.

| Run / `result.json` | SHA-256 |
| --- | --- |
| `box-preparation-v3` | `c6cace31d7ec7e01de7b079bdfbac457e0a5fd85aa7913f5c5871edc43a93116` |
| `containment-grouping-simulation-v1` | `02413cdaabaa73710ac7c1665a2550ad4d19b26a09feb1a44816395fc61b9bab` |
| `density-anchor-simulation-v1` | `640a3538df3f20580eb7dd0a3b4132b150155688f1c2249dce352a65713c2023` |
| `tiered-anchor-regions-v1` | `b22e3ecdab6546073d234e391e3f3470915fd481389de84930782e5979b3cedb` |

## 12. Punt de partida per a un agent que reprèn l’estudi

Llegeix primer aquesta síntesi i l’[índex d’evidència](../evidence/box-preparation-v1/index.json).
Els JSON de mètodes i estadístiques, els CSV per vídeo, les discrepàncies
i els exemples visuals són còpies petites i comprovables. L’índex dona la
ruta de l’artefacte original dins de runs/calibration, SHA-256 original i SHA-256
de la còpia. Als resums JSON s’indiquen els camps conservats. Els fitxers
comprimits es poden llegir amb gzip i conserven íntegre l’artefacte indicat.
Les rutes a imatges dins del CSV continuen referides al run complet.
Els vídeos, els pesos, les traces completes, els caches i l’estat humà viu
es conserven localment. Les imatges de l’arxiu són retalls i overlays de
fotogrames reals, amb decisions humanes només quan s’indica.

| Pregunta resolta | Evidència | Decisió de l’estudi |
| --- | --- | --- |
| Baixar confiança millora disponibilitat? | Aproximació IoU dels tres vídeos i confirmació als 18 | Detector 0,001 principal i 0,002 de control |
| Fer més NMS o contenir qualsevol rectangle elimina parts? | Controls inicials de l’apartat 10 i assistent al 679 | Una altra persona pot contenir la caixa bona. Evitar supressió general |
| Què aporta ancoratge, densitat o fase residual? | Taules C, A/H i R dels apartats 4–7 | Conservar fonts i àncores fortes. R segur conserva suport feble amb cost d’àrea |
| Limitar per confiança és suficient? | Cinc millors per score, 250/1.267 a cobertura ≥90% i 27/56 humanes | El score sol prioritza altres persones |
| Com reduir amb menys pèrdua de localització? | Zona, fons fix, suport de silueta i contenció protegida | Dotze candidates com a punt de partida experimental |
| Es conserva l’ID del gimnasta? | Prova contínua, 12 vídeos i 419 referències IA visibles | Encara cal guanyar qualitat en la mesura i comprovar l’ID en finestres humanes contínues |

## 13. Llindars del detector i camí fins al perfil

El pilot inicial va fixar tres vídeos, detector YOLOv8m i NMS 0,7 amb
OC-SORT, ByteTrack, BoT-SORT i BoT-SORT amb ReID. La prova robusta va creuar
quatre confiances amb els quatre backends i va produir 48 passades de
tracking. La segona iteració va baixar de 0,01 a 0,001 amb el detector.
Les xifres següents són disponibilitat d’almenys una caixa IoU≥0,50
als mateixos 61 fotogrames visibles. La columna de volum suma tots els
actors dels tres clips sencers.

| Confiança YOLO mínima | Disponibilitat /61 | Caixes totals |
| --- | ---: | ---: |
| 0,10 | 48 | 65.586 |
| 0,05 | 48 | 106.136 |
| 0,02 | 54 | 176.668 |
| 0,01 | 56 | 219.372 |
| 0,005 | 57 | 257.737 |
| 0,002 | 59 | 328.974 |
| 0,001 | 59 | 406.609 |

Amb 0,01, ByteTrack va passar de 44 a 54 observacions compatibles i de
17 a 28 amb el millor ID fix respecte de 0,05, amb duplicats de 2 a 9.
BoT-SORT amb ReID va passar de 46 a 51 observacions i de 29 a 33 amb ID
fix. OC-SORT es va mantenir a 46 observacions. La matriu completa amb
canvis, duplicats i IDs fixos queda al [CSV de llindars](../evidence/box-preparation-v1/thresholds-tracker-grid.csv).
La confiança forta del tracker (0,10 en aquella iteració) i l’admissió
feble (0,01 als backends corresponents) són paràmetres diferents del
llindar del detector. No se’n deriva un perfil de tracking òptim.

Amb 0,001 i 0,002 el pilot empata a 59/61. A AGE3 001351 #102, 0,001
millora l’IoU de 0,513 a 0,751. A #180 s’hi veu sobretot un fragment. En
l’ampliació a 18 vídeos, 0,001 arriba a 1.204/1.267 caixes compatibles,
davant de 1.185/1.267 amb 0,002. Es manté 0,001 principal amb YOLOv8m, NMS
0,7, mida d’entrada 1280, resize 1,5 i màxim 300. Es manté 0,002 com a
control. La reserva temporal es va mirar durant l’estudi. El detector
produeix moltes persones reals del públic i deteccions parcials.
[Comparació de llindars](../evidence/box-preparation-v1/images/threshold-000709.jpg) ·
[Fragment AGE3 #180](../evidence/box-preparation-v1/images/low-threshold-partial-180.jpg) ·
[Resultat als 18 vídeos](../evidence/box-preparation-v1/expanded-localization-per-video.csv).

Sobre aquella entrada, S0 va agrupar 1.090 de les 233.299 deteccions
mostrejades i va deixar 137 de 138 alternatives locals al voltant de les
seleccions revisades. L’anàlisi de confiança va trobar 76/98 petites
contingudes amb menys score que la tria, però també 22 amb més score.
Això va motivar donar suport a bones àncores i conservar fragments febles.
Dues situacions diferents es veuen al [solapament amb un assistent](../evidence/box-preparation-v1/images/containment-assistant-679.jpg)
i a [l’àncora parcial que necessita més extensió](../evidence/box-preparation-v1/images/density-partial-889.jpg).

## 14. Llista curta i prova contínua que es va executar

El rànquing usa el component de primer pla, la seva extensió i el
percentatge que explica cada caixa. El score original i la proximitat a
la zona aporten preferències menors. La zona obligatòria deixa entrar una
caixa pel centre o si conté ≥55% de la seva pròpia àrea. La variant
flexible conserva la mateixa preferència en la puntuació i permet
candidates exteriors. El fons és la mediana de 21 fotogrames a mitja
resolució. Una absorció final necessita ≥95% de cobertura de la caixa
absorbida i IoU≥0,67 o suport de fragment del mateix component. El valor
de rànquing decideix l’ordre i el límit, i la mesura conserva el score
observat o el de llavor quan es deriva una regió.

| Variant espacial sobre 1.440 mostres | Caixes/frame | Cobertura IA ≥90% /1.267 | Caixa triada ≥95% /56 |
| --- | ---: | ---: | ---: |
| S0 | 161,3 | 1.054 | 56 |
| Contenció C amb salvaguardes | 112,0 | 1.054 | 56 |
| Híbrid H amb suport de densitat | 109,2 | 1.054 | 56 |
| R segur | 114,4 | 1.079 | 56 |
| R segur dins la zona | 87,5 | 1.079 | 56 |
| Cinc per confiança | 5 | 250 | 27 |
| Cinc amb primer pla inicial | 5 | 724 | 51 |
| Vuit amb primer pla inicial | 8 | 894 | 56 |
| Vuit substituint regions per una caixa observada | 8 | 828 | 52 |
| Vuit amb més pes d’extensió | 8 | 1.061 | 56 |
| Vuit amb extensió i contenció protegida | 8 | 1.065 | 56 |
| Dotze amb extensió i contenció protegida | 12 | 1.078 | 56 |
| Dotze amb extensió i sense contenció final | 12 | 1.078 | 56 |

El [resum de les 23 variants](../evidence/box-preparation-v1/shortlist-spatial-summary.json)
inclou també límits 16, la plaça reservada per a un possible assistent i
els controls sense la segona fusió. Reservar plaça a l’assistent no va
millorar la disponibilitat. Als dotze, la contenció protegida empata amb
només rànquing en cobertura final. Les tres primeres places passen de
775 a 798 cobertures IA. El fons també reacciona a la lona i al públic
en moviment. [Fons i components](../evidence/box-preparation-v1/images/foreground-comparison.jpg) ·
[Guanys del pes d’extensió](../evidence/box-preparation-v1/images/shortlist-recoveries.jpg) ·
[Regions que encara incorporen fons](../evidence/box-preparation-v1/images/shortlist-regions.jpg).

La prova contínua va processar 12 clips complets, 10.440 fotogrames,
48 passades amb el mateix ByteTrack i 419 referències IA visibles en
sis clips. Els sis nous tenen mostres per anotar. ByteTrack va usar forta
0,05, feble 0,001, confirmació en tres mesures i retenció nominal 0,5 s.
Els denominadors següents són els 419 fotogrames visibles. Les mesures
observades i les prediccions es van registrar separadament.

| Variant | Candidates/frame | Cobertura ≥90% | Candidata IoU≥0,50 | Track observat IoU≥0,50 |
| --- | ---: | ---: | ---: | ---: |
| S0 | 156,3 | 348 | 394 | 360 |
| Dotze, zona obligatòria | 12 | 356 | 364 | 329 |
| Vuit, zona obligatòria | 8 | 348 | 364 | 324 |
| Dotze, zona flexible | 12 | 356 | 364 | 324 |

La reducció de volum és del 92%. Les dues variants de dotze coincideixen
en disponibilitat a IoU≥0,50, i el tall obligatori deixa fora una caixa
gran al #1179. La caixa 14a cobria el 97% i incloïa taula de jutges. La
12a deixa fora part del braç alçat i cobreix el 84%. Els 30 casos en què
S0 tenia candidata a IoU≥0,50 i la llista de dotze la perd es produeixen ja
en la fase regional. Aquest fet permet centrar una futura millora en la
geometria de la mesura abans de recalibrar el tall.
[Comparació #1179](../evidence/box-preparation-v1/images/entry-budget-1179.jpg) ·
[Regió amb massa marge, #356](../evidence/box-preparation-v1/images/tracking-geometry-356.jpg).

Per al criteri acordat d’entrada, una caixa parcial útil és acceptable
si localitza el gimnasta. En les 21 seleccions humanes prèvies dels dos
vídeos coincidents, hi ha cobertura ≥95% en totes i 14 caixes exactes.
Entre les 419 referències IA, 393 superen el diagnòstic geomètric més
permissiu (≥25% de cobertura i ≥50% de la candidata dins la referència).
A la revisió dels 26 casos restants es van observar 22 caixes àmplies que
incloïen el gimnasta, tres fragments identificables i **un cas clar
sense caixa útil**, AGE3 001351 #97. El millor solapament amb la
referència era 9% ja a la sortida original de YOLO. Aquesta revisió
és parcial. La resta de fotogrames i les sortides laterals o salts
inusualment alts continuen sense validació exhaustiva.
[Absència #97](../evidence/box-preparation-v1/images/entry-97.jpg) ·
[Fragment #180](../evidence/box-preparation-v1/images/entry-180.jpg) ·
[Fragment #510](../evidence/box-preparation-v1/images/entry-510.jpg) ·
[Caixes, ordre i referències dels exemples](../evidence/box-preparation-v1/shortlist-entry-cases.json).

L’associació ByteTrack suma 22,1 s amb S0 i 4,45 s amb dotze. El replay
conjunt triga 733 s i 650 s corresponen a la preparació compartida entre
variants. La inferència nova triga 113 s, amb sis reutilitzacions de CSV.
L’associació accelera i falta una mesura aïllada del
cost total amb el perfil representatiu. El pic del replay és 1,78 GiB de
RAM i el detector nou arriba a 382 MiB de VRAM CUDA assignada.
[Resum per vídeo i variant](../evidence/box-preparation-v1/shortlist-tracking-per-video.csv) ·
[Discrepàncies completes comprimides](../evidence/box-preparation-v1/shortlist-tracking-discrepancies.csv.gz) ·
[Comparació aparellada de les 419 mostres](../evidence/box-preparation-v1/shortlist-tracking-paired.json.gz).

La configuració adoptada per continuar és dotze amb zona obligatòria
calibrada per clip. Una caixa útil del gimnasta és el criteri d’entrada.
El perfil és explícit i es pot seleccionar al pipeline existent. Per a
plans que surtin del camp calibrat hi ha control de zona flexible.
La millora pendent és conservar una mesura corporal útil quan el suport
feble forma regions grans. La continuïtat d’ID i la transferència entre
gimnasta i assistent requereixen finestres humanes contínues. Aquestes
són preguntes noves respecte del recompte espacial que ja s’ha comprovat.

La implementació va reproduir geometria, ordre, scores i procedència de
les llistes congelades en 171 fotogrames dels 12 clips, amb tres variants
per fotograma. Són comprovacions de paritat, separades de l’avaluació de
gimnasta i d’ID. [Registre de verificació](../evidence/box-preparation-v1/implementation-validation.json).
