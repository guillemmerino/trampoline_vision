# Infraestructura d’execució i avaluació

| Mòdul | Responsabilitat |
| --- | --- |
| `paths.py` | Ubicacions compartides; resol els plans tancats des d’archive. |
| `common.py` | JSON estricte, hashes, checkpoints i bloqueig de run. |
| `run.py` | Detector/trackers sobre un pla explícit, cache i recursos. |
| `iterate.py` | Orquestra una iteració i la seva valoració. |
| `detector.py` | Adaptador YOLO del banc, sense canviar els originals. |
| `evaluation.py` | Lectura de referències i mètriques de revisió dispersa. |
| `sampling.py` | Estrats i mostreig dels fotogrames de revisió. |
| `representative.py` | Comparador històric congelat del replay de 12 clips. |

Aquest directori és infraestructura experimental. La preparació reutilitzable
de caixes és a [src/preparation](../../../src/trampoline_vision/preparation/README.md)
i el motor d’IDs a `src/trampoline_vision/tracking/`.
Els defaults històrics serveixen per reproduir plans tancats; un estudi nou
ha de declarar explícitament el seu pla. Vegeu [l’arxiu](../archive/README.md).
