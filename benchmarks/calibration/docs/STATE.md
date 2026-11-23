# Estat actual del calibratge

## Configuració de treball

- **Entrada:** deteccions enregistrades de YOLOv8m a confiança 0,001,
  NMS 0,7, imgsz 1280, resize 1,5 i max_det 300. El control històric és 0,002.
- **Preparació:** agrupament conservador, regions, silueta respecte del fons
  fix, contenció i selecció de màxim 12 candidates.
- **Zona comuna:** `[0.06, 0.25, 0.94, 0.93]`, mode `soft`. Preferència de
  rànquing amb trampolí assumit al centre; les caixes exteriors poden competir.
- **Procedència:** originals íntegres i auditoria de selecció, fusions i exclusions.
- **Pipeline executable:** [track-boxes.json](../../../configs/pipelines/track-boxes.json),
  amb preparació activada i CSV calibrat. El perfil apuntat és BoT-SORT + ReID;
  és un candidat preferent d’estudis anteriors, no un guanyador validat amb aquesta entrada.

La caixa és suport per seguir la persona: pot variar de mida o incloure marge.
La identitat ha de correspondre al gimnasta i no transferir-se a un assistent.
La reconstrucció d’esquelets i les trajectòries articulars són posteriors.

## Què s’ha contrastat

La comparació aparellada sobre 18 vídeos i 1.440 fotogrames conserva les
56 caixes útils humanes amb cobertura ≥95%. Sobre 1.267 referències IA visibles,
la cobertura ≥90% és 1078 amb les zones antigues i 1077 amb la central soft.
El cas addicional continua localitzant el gimnasta a la revisió visual, amb
menys cobertura dels braços. Les mètriques de referències humanes no canvien.
No s’ha validat exhaustivament cada fotograma ni la generalització a altres escenes.

- [Decisions i recorregut experimental](../archive/detection-preparation-v1/docs/DETECTION_DECISIONS.md).
- [Resultat de zones i limitacions](../archive/detection-preparation-v1/docs/ZONE_COMPARISON.md).
- [Variants descartades i prometedores](../archive/detection-preparation-v1/docs/BOX_PREPARATION_STUDIES.md).
- [Estat històric anterior](../archive/detection-preparation-v1/docs/STATE_HISTORY.md).

## Anotacions i revisió humana actives

[annotations/](../annotations/README.md) conserva els originals i la selecció.
Les anotacions d’IA estan acceptades per a l’estudi i continuen provisionals;
només les decisions explícites de l’usuari són revisió humana.

La pàgina de treball és `http://localhost:8766/`, iniciada amb
`python3 -m benchmarks.calibration review serve`. Les decisions es desen a
`runs/calibration/expanded-localization-v1/human-review/review-state.json`.
[Guia de revisió i revaloració](HUMAN_REVIEW.md).

## Treball següent proposat

Comparar OC-SORT, ByteTrack i BoT-SORT amb/sense ReID sobre les mateixes
candidates actuals, començant pels tres vídeos inicials. Revisar finestres
contínues per separar absència de candidata, fallada d’associació, canvi d’ID
i transferència a altres persones. El [protocol nou](../config/studies/identity-continuity-v1.md)
fixa tres vídeos complets, quatre perfils i revisió contínua; la bateria
ja s’ha executat i s’han verificat els 47 artefactes i la paritat de candidates.
La [revisió provisional](../reviews/identity-continuity-v1/README.md) troba
menys fragmentació dispersa amb BoT-SORT, una aportació modesta de ReID i
transferències a assistents també amb ReID. No hi ha guanyador validat.
S’han inspeccionat 109 frames únics, amb 46 frames de finestres curtes
contínues; falta completar les 1.620 frames de revisió del protocol.
La comanda de bateria continua fent només preflight per defecte.

El registre temporal, els quatre perfils, els descriptors i les exportacions
JSONL/MP4 ja existeixen. Els estudis previs de tracking aporten antecedents,
però no substitueixen el contrast amb la preparació actual. `recovery` disposa
d’auditoria experimental de fragments; no aplica unions definitives.
[Perfils i flux executable](../../../docs/27-configurable-box-tracking.md).

Per al tracker propi, s’ha adoptat que **totes les caixes seleccionades
(fins a 12) siguin elegibles per mantenir un ID confirmat, sense un segon
tall de confiança YOLO**. La confiança es pot usar com a cost suau i la
confirmació d’IDs nous té una política separada. [Decisió de disseny](../../../docs/decisions/0012-tracking-candidates-without-confidence-cutoff.md) · [Simulació de confiança i silueta](../config/studies/trampoline-silhouette-v1.md).

La **velocitat simple amb penalització suau de YOLO** és la base
experimental per provar el reconciliador. Es compararan les propostes
d’unió amb les traces congelades de la variant `velocity_soft_yolo`.
[Decisió sobre la base experimental](../../../docs/decisions/0013-simple-velocity-baseline-for-reconciliation.md).

El [catàleg provisional per a recovery](../config/studies/recovery-case-catalog-v1.md)
ja conté 18 finestres amb traces i clips revisables i fixa tres vídeos
de reserva. Les àncores d’actor i els límits dels trams queden pendents
de revisió humana independent.

La [prova de recovery geomètric](../config/studies/recovery-geometry-v1.md)
obté 33/45 parells d’àncores en la mateixa cadena, amb quatre guanys i
quatre pèrdues respecte dels IDs originals. En quatre cadenes coincideixen
àncores del gimnasta i d’altres actors.

La [prova del graf geomètric amb caixa inicial comuna](../config/studies/recovery-subject-path-v1.md)
ha reproduït el risc detectat en la simulació. A les àncores revisades,
el graf afavoreix espectadors, jutges i caixes mixtes, tot i que té
disponibles les candidates útils del gimnasta.
