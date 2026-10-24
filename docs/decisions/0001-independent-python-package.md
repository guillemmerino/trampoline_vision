# 0001. Paquet Python independent

Data: 2026-10-24. Estat: accepted.

## Context

El prototip anterior barreja scripts, serveis, dades i experiments. El nou desenvolupament necessita fronteres clares i imports sense efectes laterals.

## Decisió

Crear un projecte germà de TFM, amb layout src, contractes i dominis funcionals. CLI, API i worker compartiran la coordinació d’aplicació. No es requereix un microservei per domini.

## Conseqüències

El codi nou no importa scripts de TFM. Es poden reutilitzar idees revisades i dades mitjançant adaptadors. La infraestructura es pot substituir sense redefinir el significat de les observacions.

## Alternatives

Reorganitzar directament TFM o crear serveis independents per a cada domini; es descarten com a punt de partida per evitar dependències heretades i complexitat operativa inicial.
