# 28. Estructura i construcció del paquet recovery

Estat: estructura preparada; algoritmes, contractes i integració pendents.
L'acord és començar pel paquet i derivar criteris de recuperació mitjançant
intents i proves. Aquest increment crea ubicacions i responsabilitats,
no una funcionalitat activable en execució. Es manté la versió 0.5.0.

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

Els contractes hauran de preservar timestamps, caixes, candidate_id,
procedència i evidència observada/predita, així com l'estat de cada decisió.
Unir fragments no genera una mesura dins del buit que els separa.
L'absència d'una correspondència prou clara serà un resultat vàlid.

## Mapa dels fitxers reservats

| Fitxer sota `src/trampoline_vision/` | Responsabilitat futura |
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

Els fitxers Python contenen només docstrings. No s'exposen signatures,
classes o funcions provisionals que puguin semblar operatives. Els comentaris
expliquen les entrades, sortides i dependències que caldrà concretar.

## Activació i perfils

`configs/recovery/` reserva tres exemples: desactivat, geometria i geometria
amb aparença. Tots declaren `enabled: false` i `implementation_status: design-only`.
Els camps són un esborrany; canviar el booleà no activa una funcionalitat.
El pipeline actual no accepta recovery_config i no s'ha modificat.

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
la mateixa dimensió. També caldrà validar cobertura: un JSONL pot ser un
interval i no el vídeo complet que espera el primer mode global.

Ara application.tracking obté aparença quan la necessita el tracker.
En integrar recovery caldrà permetre que la demani el tracker o el
reconstructor, i compartir-ne el cache. Cada consumidor rebrà només les
dades que admeti; OC-SORT/ByteTrack no han de consumir descriptors per
poder afegir una reconstrucció posterior amb aparença.

Els resultats tindran destinacions i esquemes propis amb referències al
tracking original. La reconstrucció es podrà repetir canviant criteris
sense tornar a executar el detector o tracker, amb els inputs necessaris
disponibles. La inferència d'aparença faltant serà un cost separat i explícit.

## Ordre proposat dels increments

1. Definir contractes, invariants i configuració executable desactivada.
2. Llegir traces completes i construir fragments amb casos sintètics.
3. Implementar evidències geomètriques i generar propostes en mode audit.
4. Incorporar aparença verificada, resolució global i validació de cadenes.
5. Connectar cas d'ús, perfils, artefactes i visualització; després habilitar apply.
6. Comparar variants sobre els clips existents i refinar a partir dels errors.

Es reserven carpetes amb plans de proves a tests/unit/recovery,
tests/integration/recovery i tests/regression/recovery. Encara no contenen
tests executables. Cal mesurar unions equivocades, recuperacions correctes,
fragmentació i cobertura observada amb referències independents. No es
presentarà una trajectòria contínua visualment com a identitat validada.

## Abast d'aquest increment

S'han creat estructura, exemples i documentació, sense nous algorismes,
dependències, API pública, comandes CLI ni canvis de comportament de tracking.
No s'han executat vídeos ni reconstruït actors. El següent treball comença
amb els contractes i la construcció de fragments, no amb l'ajust d'un solver.
