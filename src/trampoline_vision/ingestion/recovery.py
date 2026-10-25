"""Espai reservat per llegir resultats de tracking destinats a reconstrucció.

Validarà esquema, vídeo/run, ordre de frames i temps, geometria, referències
i procedència dels candidats abans de convertir registres als contractes.
La lectura d'un JSONL no és suficient per assumir que conté un vídeo complet:
caldrà validar la cobertura declarada i conservar intervals/buits explícits.

L'aparença no és dins del JSONL actual: application en coordinarà la consulta
al cache amb les mateixes entrades i fingerprint. Aquest lector no decidirà
enllaços, carregarà models ni barrejarà traces de configuracions diferents.
"""
