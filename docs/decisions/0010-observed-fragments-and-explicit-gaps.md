# 0010 — Fragments observats i buits explícits abans del rematching

Estat: implementada a 0.6.0, com a primer increment de recovery.

## Context

Per comparar recuperacions necessitem unitats auditables. Un ID del tracker
pot incloure mesures, prediccions, recuperacions i fins i tot transferències
a un altre actor. Unir IDs directament amagaria aquestes diferències.

## Decisió

Adoptar consecutive_observations_v1: cada ratxa màxima de mesures públiques
consecutives d'un track és un fragment. lost/finished el tanquen; recovered
n'inicia un altre. El final de vídeo censura, no finalitza artificialment.
Les prediccions i finished queden en buits explícits amb referències als
fragments del mateix track. No s'aplica cap llindar físic ni unió entre IDs.

Exigir informe + JSONL de tracking complet, contrastats amb el vídeo original.
La preparació es publica en artefactes nous mitjançant inspect-fragments,
separada de track, i admet un perfil disabled. La sortida original es conserva.

## Conseqüències

Hi pot haver molts fragments petits. Aquesta és una base de diagnòstic,
no una estimació de quants actors hi ha ni una garantia de coherència dins
de cada fragment. Els descriptors i les transferències d'actor s'estudiaran
als passos futurs 4–6 abans de publicar reconstruccions amb actor_id.

L'historial manté mesures i prediccions diferenciades i es pot rastrejar
fins al candidat original. Els perfils de reconstrucció global continuen
de disseny; només la preparació és executable en aquesta versió.

## Alternatives

Agrupar automàticament buits breus o tallar per velocitat/confiança exigiria
fixar criteris encara no contrastats. Es podran comparar com a polítiques
versionades posteriors, conservant aquesta base sense llindars.

Vegeu [guia 29](../29-recovery-fragment-inspection.md) i [frontera 0009](0009-offline-recovery-boundary.md).
