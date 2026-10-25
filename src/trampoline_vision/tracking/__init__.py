"""Seguiment de caixes amb backends configurables i registre temporal propi.

factory selecciona adaptadors OC-SORT, ByteTrack o BoT-SORT. L’aparença
prové de perception, quan el perfil la requereix; session valida seqüència i
explicita confirmació, pèrdua, recuperació i finalització. Els contractes
són independents a contracts.tracking. Importar el domini no carrega NumPy
ni el backend: les dependències només s'activen en construir una sessió.
"""
