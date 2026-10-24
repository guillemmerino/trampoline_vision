# 0003. Observacions i temps canònics

Data: 2026-10-24. Estat: accepted.

## Context

Els formats heretats combinen numeracions, metadades i vectors de punts. Crops i rotacions poden alterar el sistema de coordenades.

## Decisió

Utilitzar píxels del fotograma original, índex intern zero-based, marques temporals explícites, esquema de punts versionat i validesa separada. Preservar observacions i estimacions com a dades diferents.

## Conseqüències

Cada adaptador valida i converteix abans de passar dades al domini. Les normalitzacions són derivades declarades. Els buits avancen el temps encara que no hi hagi persones detectades.

## Alternatives

Compartir directament arrays externs i normalitzar tot el vídeo amb extrems globals; es descarta perquè amaga semàntica, procedència i geometria.
