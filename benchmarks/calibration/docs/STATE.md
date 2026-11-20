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
encara no s’ha executat. La comanda fa només preflight per defecte.

El registre temporal, els quatre perfils, els descriptors i les exportacions
JSONL/MP4 ja existeixen. Els estudis previs de tracking aporten antecedents,
però no substitueixen el contrast amb la preparació actual. `recovery` disposa
d’auditoria experimental de fragments; no aplica unions definitives.
[Perfils i flux executable](../../../docs/27-configurable-box-tracking.md).
