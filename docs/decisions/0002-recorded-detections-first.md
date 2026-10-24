# 0002. Deteccions enregistrades com a primera entrada

Data: 2026-10-24. Estat: accepted.

## Context

Hi ha vídeos i sortides OpenPose existents. El servidor final tindrà GPU, però l’equip de desenvolupament actual no en té.

## Decisió

Construir primer el recorregut vídeo més deteccions enregistrades. La inferència futura produirà el mateix contracte intern. La multirotació forma part del disseny, sense requerir entrenament propi.

## Conseqüències

Es pot provar ingestió, tracking i segmentació localment. Els resultats d’inferència podran persistir-se i reproduir-se. Els exemples fusionats amb procedència incompleta no permeten reconstruir informació absent.

## Alternatives

Exigir un backend GPU funcional des del primer increment; es posposa perquè no és necessari per construir els dominis posteriors.
