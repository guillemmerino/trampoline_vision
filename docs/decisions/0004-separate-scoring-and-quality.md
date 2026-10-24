# 0004. Separar puntuació esportiva i qualitat

Data: 2026-10-24. Estat: accepted.

## Context

L’objectiu final és un diagnòstic des de vídeo 2D, però el primer lliurable resol seguiment i salts. Encara no hi ha un benchmark esportiu formal.

## Decisió

Preparar el domini de puntuació com a extensió versionada. No generar notes simulades. La qualitat indica evidència disponible i no equival a probabilitat d’encert esportiu.

## Conseqüències

Les anotacions S1…S10 queden separades del processament visual. Cada avaluador futur declararà requisits, escala i unitat d’avaluació. Els valors absents es diferencien de zero.

## Alternatives

Connectar una puntuació provisional sense validació o exigir reconstrucció 3D abans de començar; cap d’aquestes opcions forma part del primer abast.
