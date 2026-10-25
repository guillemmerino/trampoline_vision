"""Espai reservat per construir fragments a partir de resultats del tracker.

Conservarà track_id, candidate_id, temps originals, caixes, evidència i
procedència. Resumirà inicis/finals observats i mantindrà els buits i les
prediccions distingits de les mesures. Un estat lost pot coexistir amb un
fragment nou: no caldrà esperar finished per considerar una continuació.

La futura política de divisió d'un track sospitós serà explícita; un mateix
track_id pot haver passat a un altre actor. Ni un buit ni una predicció
constitueixen, per si mateixos, una observació nova de la persona.
"""
