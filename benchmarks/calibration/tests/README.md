# Comprovacions del banc

Les proves cobreixen plans acotats, integritat i represa, mostreig, revisió
humana, preparació i comparació de zones amb inputs sintètics.
`test_layout.py` comprova entrades, ubicacions i compatibilitat de navegació.

Amb les dependències de calibratge instal·lades:

```bash
PYTHONPATH=src python3 -m unittest discover -s benchmarks/calibration/tests -v
```

No són una bateria d’inferència sobre els vídeos reals. Els fitxers temporals
no s’han de guardar com a evidència científica ni a l’arxiu d’estudis.
