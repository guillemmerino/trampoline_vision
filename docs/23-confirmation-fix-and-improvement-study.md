# 23. Correcció de confirmació i estudi de millores

## Resultat de la iteració

La versió **0.4.0** corregeix la reconfirmació descoberta al
[baseline 0.3.0](22-first-tracking-baseline-review.md). Una identitat confirmada
torna a `observed` amb la primera mesura reassociada; no es torna a exigir una
ratxa de tres mesures per exposar-la. El naixement continua filtrat per una
ratxa configurable de mesures consecutives. Ho verifiquen 95 proves en Docker,
inclosa una regressió amb el backend real i `confirmation_frames=3`.

S'han repetit 0–3 s i 14–17 s i estudiat tres variants, una modificació per
variant. La correcció millora la visibilitat de les associacions, però **encara
hi ha fragmentació i canvi d'actor**. Cap dels experiments de configuració
justifica canviar els defaults de confiança, deduplicació o suport parcial.
L'increment de tracking encara no supera l'acceptació sobre aquest cas real.

## Canvi de comportament i compatibilitat

`OCSortBackend` fixa `minimum_consecutive_frames=1`. Això evita que la
biblioteca oculti mesures de recuperació d'un track existent. `TrackingSession`
manté una ratxa per als IDs externs encara pendents i només crea la identitat
pública quan arriba a `confirmation_frames`.

- La primera detecció que el backend retorna amb -1 no suma a la ratxa: encara
  no sabem a quina identitat externa atribuir-la sense inventar correspondències.
- Un fotograma sense associació interromp la ratxa d'un naixement pendent.
- Un pendent que expira no genera `confirmed`, `lost` ni `finished` públics.
- Una identitat ja confirmada no perd la confirmació; un miss genera `lost`
  i la primera reassociació genera `recovered` amb mesura i timestamp actuals.
- Si el backend expira la identitat, la mostra `finished` s'emet una sola vegada.
- No hi ha excepció per confirmar anticipadament al principi del vídeo ni
  reconstrucció retrospectiva d'observacions anteriors a la confirmació.

`confirmation_policy="birth_streak_v1"` identifica la nova política, s'inclou
al JSON de pipeline i a la configuració efectiva. L'informe registra també el
mínim intern 1 i el nombre d'IDs externs pendents al final.

Els noms de camps i la forma JSONL continuen sent 1.0, però la política
operativa ha canviat i el paquet puja de 0.3.0 a 0.4.0. Amb 0.4.0, una
configuració que ometi `confirmation_policy` resol el nou default; no reprodueix
el comportament de 0.3.0. Per repetir el baseline antic cal conservar el runtime
antic i els seus artefactes. Els números d'ID no es comparen entre versions.

## Comparació amb les mateixes àncores

S'han conservat les 22 anotacions pilot, sense canviar-les segons el resultat.
La taula mostra associacions exportades de **propostes concretes**, no precisió
sobre tots els fotogrames ni cobertura exhaustiva del gimnasta. Al fotograma
45 existeixen propostes alternatives, limitació documentada al cas pilot.

| Variant | Gimnasta 0–3 s | Gimnasta 14–17 s | IDs del gimnasta en matches de vol | Observacions globals 0–3 / 14–17 s |
| --- | --- | --- | --- | --- |
| 0.3.0 anterior | 0/4 | 3/6 | 3 | 2.315 / 2.352 |
| 0.4.0 corregida | 2/4 | 5/6 | 3 | 2.743 / 3.017 |
| Corregida + confiança 0.05 | 1/4 | 4/6 | 4 | 3.903 / 3.926 |
| Corregida + deduplicació activada | 2/4 | 5/6 | 3 | 2.743 / 3.017 |
| Corregida + `require_core=false` | 2/4 | 5/6 | 3 | 2.743 / 3.017 |

El nombre de mostres predites/perdudes disminueix de 1.828 a 1.202 al primer
tram i de 2.146 a 1.481 al segon després de la correcció. Això també reflecteix
el canvi de semàntica d'exportació: no demostra per si sol millor identitat física.

Al tram de vol, el gimnasta encara apareix amb `ocsort:64`, `ocsort:184` i
`ocsort:195` en les àncores assignades. `ocsort:64` s'observa sobre el gimnasta
al fotograma 420 i sobre l'assistent del fons al 450. La confusió continua,
encara que el número sigui diferent del 65 del runtime antic.

## Què mostren els experiments

### Baixar globalment la confiança no és una millora demostrada

Amb 0.05 augmenten les associacions globals, però empitjoren les àncores del
gimnasta i hi ha més IDs diferents al tram de vol. Les confirmacions passen
de 74 a 114 al primer tram i de 26 a 45 al segon. Això és compatible amb més
naixements fragmentats o espuris, però no els classifica tots sense anotació
exhaustiva. També persisteix un ID compartit entre gimnasta i assistent.

Per tant, es manté 0.1 per defecte. Recuperar evidència feble no hauria
d'implicar donar-li el mateix poder per crear identitats noves.

### La deduplicació actual no ha actuat

Activar-la amb els llindars existents no agrupa cap candidat dels intervals
exportats. Els registres normalitzats, excloent només `run_id`, són idèntics
als de la variant corregida. Això no demostra absència de duplicats.

El parell visualment atribuït al mateix gimnasta `45:1`/`45:81` té IoU de
les extensions sense padding ≈0.514, sota el mínim 0.7. Comparteix 24 noms,
però la màxima distància normalitzada d'un punt compartit és ≈1.233, molt
superior al màxim 0.08. Les etiquetes i geometries de les propostes poden
diferir molt, tot i correspondre espacialment al mateix actor.

No es recomana abaixar indiscriminadament aquests dos límits: també es podrien
fusionar persones properes. Cal comparar criteris amb punts robustos i marcar
atribucions ambigües, incloent casos negatius de persones diferents solapades.

### Deixar de requerir core tampoc ha actuat

Amb la resta de criteris iguals, els registres també són idèntics al corregit.
S'ha precisat el diagnòstic de `450:85`: els seus cinc noms observats són
`left_knee`, `left_ankle`, `left_big_toe`, `left_small_toe` i `left_heel`.
Tots pertanyen a `legs`. A més de no tenir core, incompleix
`min_anatomical_groups=2`; treure només core no li dona una caixa.

La revisió visual atribueix aquests punts a la zona del gimnasta, però la
semàntica anatòmica no correspon necessàriament a les parts que sembla ocupar
a la imatge. No s'ha determinat si això prové del model o del processament
heretat. No es pot certificar una pose només per comptar cinc punts.

## Millores que prioritzaria

1. **Anotació independent de les propostes.** Afegir caixes manuals o llistes
   de propostes alternatives per persona i instants al voltant de la confusió
   gimnasta/assistent. El pilot actual pot comptar miss si s'ha seguit una
   altra proposta correcta; cal evitar que això dirigeixi el tuning.
2. **Qualitat geomètrica abans del tracker.** Estudiar punts extrems,
   articulacions repetides o incoherents i barreja d'actors. Contrastar caixes
   robustes o components de pose coherents, amb criteris invariants a rotació.
   Una caixa petita parcial ha de mantenir l'etiqueta de parcialitat; no s'ha
   de presentar com a cos complet ni eliminar-ne silenciosament les fonts.
3. **Separar naixement fort i manteniment feble.** La correcció ja separa
   confirmació temporal, però la confiança encara té un únic llindar d'OC-SORT.
   Un experiment ByteTrack pot comprovar una segona associació de caixes febles
   a tracks existents. El seu article proposa precisament aquesta recuperació
   de deteccions de confiança baixa, però no resol absència de caixa ni
   semàntica de pose incorrecta. [Article original](https://arxiv.org/abs/2110.06864).
4. **Coherència temporal i discriminació entre actors.** Mesurar canvis
   injustificats de mida/moviment i transferències a un assistent gairebé
   estàtic. Qualsevol cost afegit ha d'admetre inversions i agrupaments i tenir
   contraexemples. Una predicció més llarga no impedeix per si sola un canvi d'actor.
5. **Procedència de percepció i revisió per orientació.** Preservar cada
   orientació i transformació en noves inferències. El ZIP fusionat actual no
   permet saber quina orientació aporta el punt erroni. Les entrades alternatives
   `_json.zip` i `_json2.zip` existents tenen 2.790 registres `frame_*_det*`,
   no un JSON global per fotograma; no són substituts directes sense validar
   agrupació, coordenades de crop i els seus offsets.

Cap d'aquestes hipòtesis s'ha incorporat silenciosament al baseline. Les
variants de confiança, deduplicació i suport parcial queden com a experiments
separats i no s'han promocionat a configuració per defecte.

## Artefactes i reproducció

A `runs/tracking-study-02/` hi ha vuit informes i JSONL, les seves vuit
avaluacions, els dos MP4 corregits, la comparació i un mosaic abans/després.
Els vídeos corregits han passat verificació de fotogrames, dimensions, PTS i
durada. No s'ha tornat a processar el clip complet ni entrenat cap model.

Les configuracions exactes estan versionades a
[study-02/configs](../benchmarks/cases/JPN_AGE_1_000905_31.0/study-02/README.md).
Necessiten un muntatge de només lectura a `/experiments`; mantenen el manifest
de cas empaquetat i no modifiquen originals. El comparador només llegeix
informes i exportacions ja generades:

```powershell
python benchmarks/cases/JPN_AGE_1_000905_31.0/study-02/compare.py --runs runs --output runs/tracking-study-02/comparison-new.json
```

Per repetir la variant corregida amb el pipeline per defecte, reconstruir el
runtime 0.4.0 i usar noms nous:

```powershell
docker compose --profile tracking build tracking tests-tracking
docker compose --profile tracking run --rm tests-tracking
docker compose --profile tracking run --rm tracking track --config configs/pipelines/track-openpose.json --start 0 --end 3 --output runs/fixed-next-baseline.json --video-output runs/fixed-next-baseline.mp4
docker compose --profile tracking run --rm tracking track --config configs/pipelines/track-openpose.json --start 14 --end 17 --output runs/fixed-next-flight.json --video-output runs/fixed-next-flight.mp4
```
