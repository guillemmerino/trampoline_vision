# Registre de decisions arquitectòniques

Els ADR expliquen una decisió, el context i les conseqüències. Estat `accepted` significa que
la decisió guia el desenvolupament; no significa que totes les funcionalitats estiguin implementades.

| ADR | Estat | Decisió |
| --- | --- | --- |
| [0001](0001-independent-python-package.md) | accepted | Paquet Python independent amb dominis funcionals. |
| [0002](0002-recorded-detections-first.md) | accepted | Reproducció de deteccions abans d'inferència integrada. |
| [0003](0003-canonical-observations-and-time.md) | accepted | Coordenades originals i temps explícit. |
| [0004](0004-separate-scoring-and-quality.md) | accepted | Separar qualitat visual i puntuació esportiva. |
| [0005](0005-ocsort-library-and-tracking-boundary.md) | accepted | OC-SORT via trackers 2.6.1 com a baseline i contractes independents. |
| [0006](0006-tracking-session-and-sparse-review.md) | accepted | Sessió temporal amb confirmació pública, exportació i revisió dispersa. |
| [0007](0007-confirm-births-without-reconfirmation.md) | accepted | Confirmar només naixements; substitueix la política de confirmació de 0006. |

Per una decisió nova: número següent, títol, data, estat, context, decisió, conseqüències i
alternatives. Si queda substituïda, conservar el document i referenciar el nou ADR. Els
models i criteris de selecció continuen oberts. El primer tracker té una decisió explícita,
però la seva eficàcia sobre trampolí encara s'ha de mesurar.
