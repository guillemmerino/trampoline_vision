"""Espai reservat per comparar fragments i resoldre enllaços compatibles.

Construirà parelles dirigides de final a inici segons temps, exclusivitat i
evidència; calcularà costos parcials i permetrà deixar fragments sense unir.
Una finestra màxima de desaparició limitarà arestes, no tallarà el vídeo.

L'algoritme hongarès és un primer candidat de resolució, no l'orquestrador.
La formulació haurà de representar explícitament unions prohibides, costos
de no unir i alternatives ambigües. La compatibilitat d'una cadena completa
es comprovarà a validation; els pesos i llindars es derivaran de proves.
"""
