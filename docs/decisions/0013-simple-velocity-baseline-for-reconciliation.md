# ADR 0013 — Velocitat simple com a base experimental del reconciliador

Data: 2026-11-21  
Estat: `accepted` per a les proves del reconciliador.

## Context

Amb la mateixa admissió de caixes febles, el predictor de velocitat simple
va mantenir el mateix ID en 127 de 202 parells anotats i el predictor de vol
en va mantenir 123. Tots dos van observar 167 de 179 instants amb candidata
compatible. Amb la penalització suau de YOLO, la velocitat simple va arribar
a 134 de 202 parells i 169 de 179 observacions. Els parells mesuren identitat
als extrems de les anotacions disperses. Els contactes simulats encara
mostren casos en què l’ID es manté sobre un altre actor. [Comparació de predictors](../../benchmarks/calibration/config/studies/trampoline-tracker-prototype-v1.md) · [Prova de confiança i silueta](../../benchmarks/calibration/config/studies/trampoline-silhouette-v1.md)

## Decisió

Fixem **velocitat simple amb penalització suau de YOLO** com a base
experimental per provar el reconciliador. Les caixes seleccionades són
elegibles per mantenir un ID confirmat d’acord amb l’ADR 0012. [Admissió sense tall de confiança](0012-tracking-candidates-without-confidence-cutoff.md)

La referència congelada és la variant `velocity_soft_yolo` de
`runs/calibration/trampoline-silhouette-v1/`. Les assignacions originals
dels tres vídeos són a `real-traces.jsonl.gz`. El control de cada prova ha
de fer servir la mateixa sortida abans d’aplicar cap reconciliació.

## Conseqüències i alternatives

La primera prova reutilitzarà l’auditor per proposar unions entre fragments
amb evidència que pertanyen al mateix gimnasta. Una transferència sospitosa
a un assistent obliga a revisar l’interval abans d’unir-lo. Els casos dubtosos
queden pendents. L’avaluació en vídeos reservats comptarà els buits
reconciliats correctament, les unions falses i la cobertura observada.
L’elecció del predictor és experimental i es pot revisar si l’avaluació
mostra que els fragments són massa contaminats. La cerca al voltant de
l’última caixa amb YOLO suau queda com a control alternatiu, perquè en
simulació va acumular menys assignacions a altres actors. [Auditoria de recuperació](../30-experimental-recovery-audit.md)
