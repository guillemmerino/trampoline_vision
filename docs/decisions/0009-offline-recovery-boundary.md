# 0009 — Reconstrucció separada després del tracking complet

Estat: disseny adoptat; estructura creada, implementació pendent.

## Context

Els trackers de caixes poden fragmentar una persona en diversos IDs o
transferir un mateix ID a un altre actor. El producte processa vídeos
complets i permet considerar evidència posterior abans de reconstruir
trajectòries, sense requerir una resposta en temps real.

## Decisió

Reservar un domini recovery posterior al tracking acabat. El primer mode
serà offline i global, amb restriccions temporals als enllaços possibles.
Es conservaran track_id i les dades originals; fragment_id i actor_id
representaran la reconstrucció. El mòdul serà configurable i desactivable
quan estigui implementat, amb fases d'auditoria abans d'aplicació.

Separar fragments, moviment, aparença, coherència, associació i validació.
L'hongarès és un candidat de solver, no una obligació arquitectònica ni
una demostració de fiabilitat. Els criteris es derivaran d'intents i proves.

## Conseqüències

La sortida del tracker es mantindrà auditable i la reconstrucció es podrà
repetir independentment. Caldrà lectura validada de traces i accés a
descriptors verificats quan la reconstrucció els demani. Els perfils
actuals de recovery són design-only, tots desactivats, i la CLI no els consumeix.

## Alternatives

La recuperació local per finestres es podrà comparar posteriorment. No es
declara que la reconstrucció global sigui superior sense evidència. Integrar
tota la recuperació dins del backend dificultaria comparar-la entre trackers
i revisar les decisions originals.

Detall al [document 28](../28-recovery-package-design.md).
