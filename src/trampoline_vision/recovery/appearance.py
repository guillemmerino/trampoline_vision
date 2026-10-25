"""Espai reservat per resumir i comparar aparença de fragments i actors.

Consumirà descriptors de contracts.appearance, referenciats per candidat i
fingerprint del model. Prepararà galeries basades en observacions fiables i
costos de compatibilitat, amb política explícita per a evidència insuficient.

No carregarà OSNet ni llegirà el cache directament: perception extreu vectors
i application coordina la seva obtenció. No barrejarà fingerprints diferents
ni reforçarà una galeria amb prediccions o caixes de qualitat dubtosa.
"""
