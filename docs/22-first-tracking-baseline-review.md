# 22. Primera prova real del tracking i estudi del baseline

## Resultat

El recorregut tècnic funciona sobre els dos trams reals, però **el baseline
0.3.0 no conserva prou bé la identitat del gimnasta per donar el tracking per
validat**. S'han observat fragmentació, canvi d'identitat entre persones i
evidència parcial que no arriba a produir una mesura admissible.

La revisió també ha revelat una limitació de la integració amb la política de
reconfirmació d'OC-SORT: algunes associacions internes no s'exposen al nostre
registre temporal. Cal resoldre aquesta semàntica abans de tractar els totals
lost/predicted com una mesura de pèrdua visual real.

No s'han modificat algoritmes, llindars ni configuracions per obtenir aquests
resultats. La deduplicació continua desactivada. TFM i els originals s'han
muntat només per a lectura; no s'ha processat el clip complet de nou.

## Execucions i artefactes

| Execució | Índexs exportats | Escalfament | Fotogrames | Temps del cas d'ús |
| --- | --- | --- | --- | --- |
| `tracking-baseline-01` | 0–89, 0–3 s | 0 | 90 | 16.31 s |
| `tracking-flight-01` | 420–509, 14–17 s | 420 | 90 | 26.13 s |

Mesures en Docker Linux CPU, paquet 0.3.0 i trackers 2.6.1. El temps inclou
codificació i sondeig de sortida, i al segon cas escalfament des del principi;
exclou el sondeig inicial de la CLI. Les dues execucions s'han fet en paral·lel,
de manera que no són un benchmark de rendiment ni una comparació neta de costos.

Per a cada nom hi ha `.json`, `.frames.jsonl` i `.mp4` dins de `runs/`.
Els dos MP4 tenen 960×1144 píxels, 90 fotogrames i 3 s, sense àudio.
ffprobe confirma el recompte, dimensions, timestamps i durada. Error màxim
temporal: 0 s al primer i aproximadament 1.8e-15 s al segon, per representació
numèrica. Això no certifica l'exactitud anatòmica ni la identitat.

A `runs/tracking-review-01/` hi ha mosaics originals/comparats, plaques de
propostes individuals, evidència del canvi d'identitat, anotacions pilot i
el cas mínim de reconfirmació. Les imatges i vídeos són artefactes locals
ignorats per Git; els JSON petits d'anotació i el reproduïdor són a
[benchmarks/cases/JPN_AGE_1_000905_31.0](../benchmarks/cases/JPN_AGE_1_000905_31.0/README.md).

## Comptatges globals: totes les persones i tot el soroll

| Comptatge acumulat | 0–3 s | 14–17 s |
| --- | --- | --- |
| Deteccions/candidats originals | 9.385 | 8.705 |
| Candidats sense mesura | 4.120 | 3.969 |
| Candidats amb score sota 0.1 | 2.151 | 1.528 |
| Sense confirmar o sense associació exposada | 799 | 856 |
| Mostres amb associació observada exportada | 2.315 | 2.352 |
| Mostres exportades com a predites/perdudes | 1.828 | 2.146 |
| Esdeveniments de confirmació | 78 | 26 |
| Esdeveniments de finalització | 29 | 31 |

No són persones úniques ni mètriques del gimnasta. Un actor pot aportar
diversos duplicats, tracks i mostres; les múltiples causes de manca de caixa
també poden coincidir. No hi ha registres JSON absents als trams exportats.

## Evidències concretes

### Hi ha detecció suficient i confiança alta, però l'associació no s'exposa

Les propostes `15:1`, `30:9` i `45:1` corresponen visualment al gimnasta i
tenen scores aproximats 0.547, 0.450 i 0.482. Tenen mesura rectangular i
superen 0.1, però queden `unconfirmed_or_unmatched`.
Per tant, abaixar el llindar no resol aquestes absències de l'exportació.
La política de confirmació/reconfirmació i l'associació temporal s'han d'estudiar.

Al fotograma 45 la proposta alternativa `45:81` sí que s'assigna a `ocsort:61`.
Cal distingir un miss d'una proposta concreta d'un miss de totes les propostes
de la persona. Aquest fet limita la interpretació de l'avaluador pilot actual.

### Hi ha evidència del gimnasta que la preparació deixa sense caixa

Al fotograma 450, `450:85` té 5 punts observats a la zona del gimnasta. Es
conserva, però `require_core` impedeix obtenir mesura per falta d'ancoratge
anatòmic. `450:88` té 3 punts i també falla el mínim de punts.
No és correcte resumir aquest cas dient que OpenPose no ha detectat res.
Tampoc es pot afirmar que aquests fragments siguin una pose completa correcta.

Al fotograma 89, `89:26` segueix espacialment el gimnasta amb 17 punts i una
mesura disponible, però score 0.0783; queda sota el llindar 0.1 del tracker.
Aquesta és una causa diferent que sí que necessita comparar polítiques de
confiança, sense assumir que baixar-la globalment no augmentarà el soroll.

### Alguns punts erronis fan caixes poc representatives

`60:73` conté evidència del gimnasta però també un punt molt llunyà: la caixa
derivada s'estén aproximadament entre Y=202 i Y=662. `75:17` amplia la caixa
fins a X≈505 per punts que no representen bé el cos del gimnasta.
Una caixa gran d'aquest tipus pot afectar moviment i solapament temporal.
L'indicador mitjà i comptar punts no certifiquen suport geomètric coherent.

Les propostes individuals també mostren punts de públic/jutges i connexions
entre actors. No s'ha determinat en aquest estudi quina part ve del model i
quina del processament/fusió heretat: falta la procedència per orientació.

### Canvi d'identitat verificat entre gimnasta i assistent

| Fotograma | Detecció original | Actor revisat visualment | Track exportat |
| --- | --- | --- | --- |
| 420 | `420:3` | Gimnasta en vol | `ocsort:65` |
| 420 | `420:12` | Assistent darrere del trampolí | `ocsort:162` |
| 450 | `450:85` | Fragment del gimnasta en vol | Sense caixa/assignació |
| 450 | `450:7` | Mateix assistent del fons | `ocsort:65` |
| 465 | `465:65` | Gimnasta invertit | `ocsort:138` |
| 509 | `509:58` | Gimnasta invertit | `ocsort:147` |

Entre aquests instants hi ha hipòtesis predites i possibles mesures amb ID
ocult durant reconfirmació. No s'atribueix un instant únic de canvi a partir
de les mostres disperses. La identitat incorrecta entre 420 i 450 sí que és
observable, independentment d'aquesta incertesa temporal.
Placa: `runs/tracking-review-01/identity-handoff.jpg`.

## Limitació descoberta: reconfirmació de la biblioteca i semàntica del nostre registre

El codi publicat a la wheel 2.6.1, `OCSORTTracklet.resolve_tracker_id`, retorna
-1 si el comptador d'actualitzacions consecutives no arriba al mínim, també
quan el track ja tenia una identitat confirmada. Després d'un miss es reinicia
el comptador. Mentrestant, `update` del track pot assimilar mesures reals i
`tracked_objects` continua exposant la identitat i el seu estat estimat.

El nostre adaptador només coneix la correspondència actual si `update`
retorna un ID confirmat. Si rep -1, la sessió conserva el track com lost/predicted
i no pot atribuir-li aquella detecció mitjançant l'API utilitzada. Això és
conservador respecte de la procedència, però **la caixa no està garantida com
a predicció sense cap mesura nova del backend**. `last_observed_timestamp_s`
és de fet l'última associació exposada al nostre domini, que pot diferir de
l'última actualització interna. El pressupost intern també pot renovar-se
mentre el nostre registre continua indicant perdut.

S'ha reproduït sense vídeo, amb una pose immòbil de confiança 0.9:

- Fotogrames 1–5: identitat observada.
- Fotograma 6: únic fotograma sense detecció.
- Fotogrames 7–8: detecció novament present, però exportació lost/predicted.
- Fotograma 9: la mateixa identitat torna a observed.

`confirmation_probe.py` i `confirmation-probe.json` preserven el cas mínim.
Les proves d'integració anteriors de recuperació empraven confirmació 1;
no cobrien aquest comportament específic del valor 3 del baseline.
Les 91 proves tècniques passen, però aquest estudi ha trobat una bretxa de
semàntica i cobertura de proves que cal corregir abans d'acceptar el tracking.

## Anotacions pilot i mètriques limitades

Hi ha 22 àncores revisades per l'assistent sobre originals i propostes
individuals: 10 del gimnasta i 12 de l'assistent del fons. No hi ha validació
independent ni anotació exhaustiva. No s'han usat ROIs per filtrar el baseline;
els retalls només han ajudat a revisar les imatges.

| Tram / subjecte | Àncores amb associació exportada | IDs diferents en matches | Canvis entre matches |
| --- | --- | --- | --- |
| 0–3 s / gimnasta | 0/4 | 0 | No mesurable sense matches |
| 0–3 s / assistent | 4/6 | 3 | 2 |
| 14–17 s / gimnasta | 3/6 | 3 | 2 |
| 14–17 s / assistent | 6/6 | 2 | 1 |

La primera fila **no és una cobertura 0% del gimnasta**: `45:81` és una proposta
alternativa assignada de la mateixa persona. Les dades mesuren només les àncores
escollides. També estan afectades per la reconfirmació descrita. Són diagnòstics
pilot, no HOTA/IDF1/MOTA, i no serveixen per classificar ara dos algoritmes.

Resultats locals: `tracking-baseline-evaluation-01.json` i
`tracking-flight-evaluation-01.json`, a `runs/`.

## Ordre recomanat per a la propera iteració

1. **Corregir la frontera d'associació/confirmació.** Afegir el cas mínim a les
   proves i separar confirmació de naixement de manteniment d'una identitat.
   Una via a prototipar és obtenir associacions públiques sense reconfirmació
   repetida i aplicar confirmació pròpia de naixements. Cal mesurar-ne també
   els falsos naixements; no canviar simplement 3 per 1 i donar-ho per resolt.
2. **Millorar les anotacions de revisió.** Acceptar diverses propostes correctes
   per persona/fotograma o afegir caixes manuals independents. Mantenir les
   àncores actuals i la revisió visual com a evidència, sense ajustar-les al resultat.
3. **Comparar preparació geomètrica i confiança.** Estudiar punts extrems,
   suport parcial i admissió feble per mantenir identitat; conservar sempre
   les fonts. No relaxar alhora tots els criteris ni fabricar poses completes.
4. **Provar deduplicació com a experiment separat.** Ja hi ha evidència de
   propostes alternatives, però la similitud de caixes no garanteix mateixa
   persona i les etiquetes anatòmiques poden ser incoherents en dades heretades.
5. **Comparar ByteTrack amb les mateixes entrades corregides**, si la gestió
   d'evidència feble continua essent el límit. Un altre tracker no arregla
   automàticament caixes contaminades o absència de mesura.
6. Repetir els dos trams amb anotacions fixes; després executar el clip complet.
   La selecció del gimnasta i els salts vindran quan el seguiment sigui prou fiable.

## Comandes del baseline

```powershell
docker compose --profile tracking build tracking
docker compose --profile tracking run --rm tracking track --config configs/pipelines/track-openpose.json --start 0 --end 3 --output runs/tracking-baseline-01.json --video-output runs/tracking-baseline-01.mp4
docker compose --profile tracking run --rm tracking track --config configs/pipelines/track-openpose.json --start 14 --end 17 --output runs/tracking-flight-01.json --video-output runs/tracking-flight-01.mp4
```

Són les configuracions efectives utilitzades; en aquesta execució s'ha reutilitzat
la imatge de proves amb la mateixa wheel 0.3.0 i s'ha invocat la CLI del paquet.
Per repetir, usar noms nous perquè els artefactes existents es protegeixen.

```powershell
docker compose --profile tracking run --rm tracking evaluate-tracking --tracks runs/tracking-baseline-01.frames.jsonl --annotations runs/tracking-review-01/annotations-baseline-01.json --output runs/tracking-baseline-evaluation-01.json
docker compose --profile tracking run --rm tracking evaluate-tracking --tracks runs/tracking-flight-01.frames.jsonl --annotations runs/tracking-review-01/annotations-flight-01.json --output runs/tracking-flight-evaluation-01.json
```

Aquest document registra l'estudi del baseline, incloses les seves fallades;
no substitueix la [guia d'ús](21-tracking-validation-guide.md).
