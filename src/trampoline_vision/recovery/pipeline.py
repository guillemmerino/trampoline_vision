"""Espai reservat per orquestrar la reconstrucció després del tracking complet.

Rebrà la seqüència d'un únic vídeo/run, la configuració i l'aparença opcional.
Coordinarà fragments, evidències, parelles admissibles, associació global i
validació de cadenes. Retornarà decisions i assignacions d'actor explícites.

No executarà TrackingSession per fotograma ni modificarà el tracker. Tampoc
llegirà fitxers o renderitzarà vídeos: aquests recursos pertanyen als casos
d'ús i adaptadors externs. Desactivat, el futur flux conservarà el tracking.
No hi ha encara una classe pública ni una reconstrucció implementada.
"""
