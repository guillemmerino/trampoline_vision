"""Espai reservat per al cas d'ús de reconstrucció sobre tracking acabat.

Coordinarà lectura de traces, comprovació d'identitat d'inputs, aparença
opcional, pipeline de recovery i publicació d'artefactes nous. Podrà servir
una futura CLI o l'API sense que el domini depengui d'aquestes interfícies.

Compartirà extractor/cache quan calgui aparença, encara que el tracker triat
no consumeixi ReID. No tornarà a executar detectors ni el tracker per ajustar
només la reconstrucció, i protegirà els resultats originals.
El cas d'ús i la seva connexió al pipeline encara no estan implementats.
"""
