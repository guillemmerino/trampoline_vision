# 28. Estructura i construcció del paquet recovery

Estat actual: passos 1–3 implementats a 0.6.0 (contractes, lectura/fragmentació
i diagnòstic). La reconstrucció d'actors dels passos 4–6 continua pendent.
La [guia executable 29](29-recovery-fragment-inspection.md) descriu com revisar
fragments abans d'estudiar les unions. Els criteris de recuperació es derivaran
de proves; no es considera el mòdul de recovery complet o robust encara.

## Lloc dins del projecte

```text
Vídeo → deteccions → tracking complet → recovery → trajectòries d'actors
```

Recovery rebrà el tracking acabat d'un vídeo/run. La primera implementació
serà offline i global: veurà els fragments del vídeo i resoldrà enllaços
conjuntament. Una finestra màxima de desaparició limitarà parelles possibles;
no dividirà el vídeo en intervals independents. Global és una hipòtesi adequada
al processament de vídeos complets, no una millora de precisió demostrada.
El mode local per finestres podrà comparar-se després amb els mateixos criteris.

El tracker continuarà sent responsable de l'associació temporal de caixes.
La reconstrucció relacionarà fragments amb actors i conservarà la sortida
original. La selecció del gimnasta, el matching d'OpenPose, els salts i la
puntuació són dominis diferenciats i no formen part d'aquesta estructura.

## Identitats i dades previstes

- `track_id`: identitat original del tracker, dins del seu vídeo/run.
- `fragment_id`: tram analitzat, vinculat al track i a les observacions originals.
- `actor_id`: identitat reconstruïda que podrà relacionar diversos fragments.

Un fragment no equival necessàriament a tot un track: una transferència
d'actor pot passar sense canvi d'ID. La política de detecció/divisió serà
explícita i contrastada amb exemples, sense interpretar una inversió com
una prova automàtica de canvi de persona.

Els contractes de fragments ja preserven timestamps, caixes, candidate_id,
procedència i evidència observada/predita, així com l'estat de cada decisió.
Unir fragments no genera una mesura dins del buit que els separa.
L'absència d'una correspondència prou clara serà un resultat vàlid.

## Mapa de components

| Fitxer sota `src/trampoline_vision/` | Responsabilitat |
| --- | --- |
| `contracts/recovery.py` | Fragments, evidències, enllaços, decisions i trajectòries d'actor. |
| `recovery/config.py` | Valors validats, activació i opcions experimentals. |
| `recovery/pipeline.py` | Orquestració global després del tracking complet. |
| `recovery/tracklets.py` | Construcció de fragments i resums de les observacions. |
| `recovery/motion.py` | Compatibilitat de moviment i incertesa temporal. |
| `recovery/appearance.py` | Galeries i comparació de descriptors existents. |
| `recovery/coherence.py` | Trams sospitosos i prevenció de contaminació. |
| `recovery/association.py` | Parelles admissibles, costos i resolució amb opció de no unir. |
| `recovery/validation.py` | Exclusivitat, ordre temporal i coherència de cadenes. |
| `recovery/errors.py` | Errors accionables, diferents d'una associació ambigua. |
| `ingestion/recovery.py` | Lectura i validació de traces del tracker. |
| `ingestion/recovery_config.py` | Lectura de perfils i resolució de rutes. |
| `application/recovery.py` | Recursos, dades, aparença i publicació del cas d'ús. |
| `results/recovery.py` | Exportació de decisions i futura visualització d'actors. |

Contractes, configuració de fragments, pipeline de preparació, tracklets,
validació, lectors, cas d'ús i resultats ja són executables. motion, appearance,
coherence i association continuen reservats a les etapes d'unió. La validació
actual prova partició i vida del tracker; encara no valida cadenes d'actors.

## Activació i perfils

`configs/recovery/fragments.json` i `fragments-disabled.json` són perfils
executables 1.0 de la comanda inspect-fragments. Activen/desactiven la preparació,
mai un rematching. Els tres *.example.json d'associació continuen desactivats
i design-only, i són rebutjats pel lector executable. El pipeline de tracking
encara no accepta recovery_config: la preparació és un cas d'ús posterior independent.

Quan s'implementi, disabled conservarà el recorregut existent; audit
exportarà propostes i apply publicarà també la reconstrucció d'actors.
La configuració serà independent de la selecció del tracker. No es fixen
encara temps, pesos, llindars d'unió ni marges d'ambigüitat: s'obtindran
d'experiments reproduïbles i quedaran registrats amb la configuració efectiva.

La primera opció de solver és l'hongarès, però no determina l'arquitectura.
La formulació ha d'admetre enllaços prohibits i fragments sense unió; una
assignació per parelles no garanteix per si sola una cadena coherent.
La validació de trajectòries i les alternatives competidores són parts pròpies.

## Connexions que requeriran implementació posterior

El JSONL actual exporta decisions i candidats; no inclou els descriptors.
Caldrà associar-los amb els mateixos inputs i fingerprint del model, des
del cache o l'extractor actual. No s'acceptaran vectors només perquè tinguin
la mateixa dimensió. La cobertura ja es valida contra la timeline sondejada: el primer increment
rebutja intervals parcials i exigeix el vídeo complet.

Ara application.tracking obté aparença quan la necessita el tracker.
En integrar recovery caldrà permetre que la demani el tracker o el
reconstructor, i compartir-ne el cache. Cada consumidor rebrà només les
dades que admeti; OC-SORT/ByteTrack no han de consumir descriptors per
poder afegir una reconstrucció posterior amb aparença.

Els resultats tindran destinacions i esquemes propis amb referències al
tracking original. La reconstrucció es podrà repetir canviant criteris
sense tornar a executar el detector o tracker, amb els inputs necessaris
disponibles. La inferència d'aparença faltant serà un cost separat i explícit.

## Seqüència acordada de desenvolupament

1. Contractes i invariants — implementat a 0.6.0.
2. Lector de tracking complet i constructor de fragments — implementat.
3. Diagnòstic amb informe, JSONL i visualització — implementat.
4. Propostes d'enllaç amb geometria/moviment en audit — futur.
5. Aparença verificada, resolució global i validació de cadenes — futur.
6. Comparació independent i posterior habilitació d'apply — futur.

Els passos 4–6 i els seus criteris es detallen a la [guia 29](29-recovery-fragment-inspection.md).
Hi ha proves unitàries, d'integració i regressió sintètica executables a
tests/unit/recovery, tests/integration/recovery i tests/regression/recovery.
Les unions equivocades, la cobertura i la continuïtat física encara no
s'han avaluat: no hi ha actors reconstruïts en aquest increment.
