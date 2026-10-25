# 29. Primer increment de recovery: contractes, fragments i diagnòstic

Implementat a **0.6.0**. Aquest increment completa els passos 1–3 del pla:
carregar un tracking acabat, explicar-ne la fragmentació i poder revisar
qualsevol mostra sense tornar a executar el detector, tracker o ReID.
Encara no s'uneixen trajectòries ni s'assignen `actor_id`.

## Flux executable

```text
Informe de track + JSONL complet + vídeo original
    → ingestion.recovery: cobertura, context, candidats i vida d'identitats
    → TrackingTrace
    → recovery.pipeline: fragmentació + invariants
    → FragmentationResult
    → informe JSON + fragments/buits JSONL + MP4 opcional
```

La comanda independent `inspect-fragments` s'executa **després del tracking
complet**. La comanda `track` conserva el comportament anterior. El vídeo
es necessita també sense MP4 de sortida: ffprobe en contrasta la cobertura
i els timestamps. El diagnòstic no necessita biblioteques de tracking ni models;
l'overlay necessita l'extra `visualization`, ja inclòs als runtimes Docker.

## Contractes i responsabilitats

| Contracte a `contracts/recovery.py` | Necessitat |
| --- | --- |
| `TraceCandidate` | Preservar mesura, confiança, issues, IDs locals i procedència del JSONL. |
| `TraceEvent`, `TrackingTraceFrame` | Llegir transicions i validar assignació exclusiva en cada instant. |
| `TrackingTrace` | Identificar vídeo/run, ordre temporal i seqüència completa. |
| `TrajectorySample` | Vincular context i track al candidat real quan hi ha observació. |
| `TrajectoryFragment` | Ratxa de mesures consecutives amb motius de límit explícits. |
| `TrajectoryGap` | Prediccions i finalització entre/després dels fragments, sense observacions fictícies. |
| `FragmentationResult` | Font preservada, política, fragments i buits, sense actors reconstruïts. |
| `FragmentLink` | Representar futures propostes/decisions amb costos i motius; no se'n genera cap ara. |

`ingestion/recovery.py` valida els bytes llegits, els registres JSONL i la
cobertura contra el vídeo. `recovery/tracklets.py` construeix fragments i
`recovery/validation.py` comprova vida d'identitats i partició exacta de mostres.
`application/recovery.py` coordina inputs i publicació. `results/recovery.py`
produeix diagnòstic, exportació i overlay. Tots aquests components tenen
docstrings en català; importar-los no carrega xarxes ni trackers opcionals.

## Política inicial de fragmentació

`consecutive_observations_v1` és una base reproduïble, sense llindars ajustats:

1. La primera mostra pública observada d'un track inicia un fragment (`confirmed`).
2. Mesures del mateix track en frames consecutius continuen el fragment.
3. La primera mostra `lost` o `finished` tanca el fragment anterior.
4. Una recuperació del mateix track inicia un fragment nou (`recovered`).
5. Un fragment viu a l'últim frame queda censurat (`video_end`), no finalitzat.

Per tant, una sola pèrdua de mesura ja separa fragments. Això pot generar
molts fragments; aquesta versió no pretén decidir quins buits són acceptables.
Una altra política només s'introduirà amb evidència i una versió diferenciada.

```text
frame             0  1  2  3  4  5  6
track A           O  O  P  P  O  O  F
fragment A:1      └──┘
gap A:1                 └──┘
fragment A:2                  └──┘
gap A:2                             F
O: observat · P: perdut/predit · F: finished
```

El `fragment_id` és determinista per track i ordinal, dins del seu vídeo/run.
Els IDs del tracker no es modifiquen. Els buits referencien el fragment
anterior i el següent si el mateix track torna observat. **Aquesta referència
no és un rematching**: reflecteix només la continuïtat que ja declara el tracker.
Un track nou mai s'uneix amb un altre en aquest increment.

Els fragments contenen exclusivament observacions. Les prediccions amb caixa,
les prediccions sense geometria i les mostres `finished` queden preservades
als buits. `finished` no es compta com a predicció amb caixa ni cobertura
observada. No s'interpolen mesures ni esquelets dins de desaparicions.

## Requisits i errors de lectura

S'admeten informes esquema 1.0 de la comanda `track` i el seu JSONL, amb
`run_id` en cada frame. La versió de programari d'origen queda registrada.
La primera implementació exigeix frame 0 fins a l'últim del vídeo original;
les exportacions parcials es rebutgen, encara que el tracker tingués warmup.
Les traces experimentals fora d'aquest esquema necessiten un adaptador explícit.

Es comproven:

- Mateix vídeo/run, índexs consecutius, geometria i temps/durades originals.
- Claus JSON sense duplicats, valors finits i estructura compatible.
- Mesures observades iguals als seus candidats i referències/procedència vàlides.
- Candidats assignats o no assignats amb partició exclusiva.
- Transicions confirmed/lost/recovered/finished, últim temps real observat i no reutilització d'IDs retirats.
- Recompte real fins a EOF, totals declarats i tracks censurats al final.
- Hashos de vídeo/JSONL si l'informe d'origen els declara.

Els SHA-256 del vídeo, informe i JSONL utilitzats es registren al diagnòstic.
Els informes 0.5 habituals no contenen hash del vídeo ni del JSONL: se'n
comproven cobertura i consistència, però no es pot demostrar retroactivament
que els píxels siguin els mateixos que van originar les deteccions. L'informe
explicita aquesta limitació. Cap comprovació de format prova identitat humana.

## Executar

Des de l'arrel del projecte, construir el runtime amb el nou paquet:

```powershell
docker compose build replay
docker compose run --rm replay inspect-fragments --tracking-report runs/my-tracking.json --config configs/recovery/fragments.json --output runs/my-fragments.json --video-output runs/my-fragments.mp4
```

`my-tracking.json` és un informe **complet** ja produït per `track`, amb
el seu JSONL disponible. Els informes solen declarar rutes absolutes de
contenidor; si s'han mogut, es poden indicar les fonts explícitament:

```powershell
docker compose run --rm replay inspect-fragments --tracking-report runs/my-tracking.json --tracks runs/my-tracking.frames.jsonl --video /workspace/TFM/jumping_score/output_clips/JPN_AGE_1_000905_31.0.mp4 --output runs/my-fragments-moved.json
```

Les rutes relatives dins de l'informe es resolen respecte del mateix informe.
Els arguments relatius de CLI es resolen des del directori de treball.
`--fragments-output` permet canviar la destinació JSONL; per defecte és
`output-stem.fragments.jsonl`. `--video-output` és opcional. Les sortides
existents, les col·lisions i la substitució d'inputs es rebutgen.

`configs/recovery/fragments.json` és executable, esquema 1.0:

```json
{
  "schema_version": "1.0",
  "task": "inspect_tracking_fragments",
  "enabled": true,
  "policy": "consecutive_observations_v1"
}
```

Sense `--config` s'utilitza aquesta política. Amb `fragments-disabled.json`
es valida la font i es publica `status: disabled`, un JSONL buit i cap fragment.
El tracking original es conserva. Aquesta opció desactiva **la preparació**;
la futura opció de rematching continua pendent d'implementació. Els tres
`*.example.json` d'associació continuen `design-only` i el lector els rebutja.
No s'ha afegit `recovery_config` al loader del pipeline de tracking.

## Artefactes i revisió

L'informe conté política efectiva, hashes, cobertura, fragments/buits per
track i recomptes. Per fragment: límits observats, durada, caixes inicial/final,
confiança mínima/màxima/mitjana i issues originals. La confiança de la mesura
no és una probabilitat de recuperació ni una garantia de qualitat d'identitat.

El JSONL té registres `fragment` i `gap`, amb mostres, context i procedència
complets. El resum és per inspecció; aquest JSONL conserva el detall auditable.
L'ordre és per blocs, no una segona traça per fotograma. El tracking original
continua sent la referència temporal, amb el seu `tracking_run_id`.

El MP4 mostra `track_id` i l’ordinal compacte `F1`, `F2`… del fragment
d’aquell track; l’ID complet és al JSONL. Les mesures són caixes contínues;
les prediccions són discontínues i es marquen `GAP`, referint el
fragment anterior, no una observació nova. Les prediccions sense caixa no
es dibuixen i es compten per separat. No hi ha suavitzat ni selecció del gimnasta.
Es verifiquen recompte, dimensions i tots els timestamps després de codificar.

Els artefactes es preparen temporalment i només es publiquen després de
validar-los, amb l'informe al final. En errors normals de publicació es
retiren només els fitxers nous d'aquesta execució. No es promet una transacció
conjunta davant una interrupció abrupta del procés.

## Validació de l'increment

Les proves cobreixen vida d'identitats, recuperació del mateix ID, diversos
actors, absència total de tracks, ratxes d'un sol frame, censura dreta,
prediccions sense caixa, temps variables, traces truncades/barrejades,
geometria inconsistent, corrupció tardana i rollback de publicació.
La regressió sintètica amb buits irregulars comprova partició i determinisme.
La CLI i la codificació es comproven amb vídeos generats, sense models.

Verificació completada:

- 135 proves al runtime Docker amb la wheel 0.6.0 instal·lada, incloses les regressions existents.
- 104 proves disponibles passen a Python 3.10 de Windows; 31 s'ometen per capacitats opcionals absents.
- Tracking existent del clip JPN_AGE_1_000905_31.0: 930 frames, 77 IDs, 498 fragments,
  483 buits i 127 fragments d'una observació. Es conserven 14.618 observacions,
  2.186 mostres lost i 60 finished. Són tots els actors, no només el gimnasta.
- MP4 complet verificat amb error màxim de timestamps i durada igual a 0.
  S'ha revisat una imatge de les etiquetes de fragment/track i prediccions.

Artefactes locals de revisió: runs/recovery-fragments-01/review.json,
review.fragments.jsonl i review.mp4. L'entrada és l'informe/JSONL ja existent
a runs/tracking-integration-06/JPN_AGE_1_000905_31.0/reid.json. No s'han
reexecutat detector, tracker o inferència d'aparença per aquesta revisió.
Els artefactes grans queden fora de Git. Aquests recomptes són diagnòstic
de fragmentació, no mètriques de precisió ni millores de continuïtat.

Aquest increment no ofereix encara recuperació robusta d'actors. Un fragment
pot contenir una transferència a un jutge sense que el tracker canviï d'ID;
la detecció d'aquest cas exigeix coherència i evidència addicional.

## Passos futurs naturals: 4–6

**4. Propostes d'enllaç en auditoria.** Consumir fragments verificats, definir
compatibilitat temporal i espacial, estimar moviment/incertesa i exportar
possibles continuacions amb costos, alternatives i motius de rebuig. Encara
sense aplicar unions. Incloure contraexemples d'actors propers, buits llargs
i contactes amb assistents. Els llindars sorgiran de proves, no d'un valor
de confiança presentat com a universal.

**5. Aparença, resolució global i validació de cadenes.** Associar descriptors
al mateix candidat i fingerprint, gestionar galeries fiables i prevenir
contaminació per caixes mixtes. Resoldre enllaços amb opció de no unir,
preservant ambigüitat i exclusivitat. L'hongarès serà un primer candidat,
substituïble si la formulació ho requereix. Comprovar coherència de cadena,
no només costos entre dues puntes; estudiar subdivisions de tracks sospitosos.
Aquí arribarà l'assignació provisional d'actor_id, separada de track_id.

**6. Comparació independent abans d'apply.** Comparar disabled, geometria i
geometria+aparença sobre els mateixos trackings dels tres clips. Mesurar
unions correctes/equivocades, fragmentació, cobertura observada, ambigüitat
i cost, amb anotacions que no provinguin del reconstructor. Una trajectòria
visualment contínua no és prova d'identitat. Només habilitar aplicació després
de revisar errors i conservar el baseline; després podrà arribar el matching
de poses i la segmentació de salts sobre trajectòries amb qualitat coneguda.
