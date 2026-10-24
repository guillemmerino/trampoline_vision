"""Seguiment de candidats amb OC-SORT i registre temporal propi.

backend adapta trackers 2.6.1 sense pesos; session valida seqüència i
explicita confirmació, pèrdua, recuperació i finalització. Els contractes
són independents a contracts.tracking. Importar el domini no carrega NumPy
ni el backend: les dependències només s'activen en construir una sessió.
"""
