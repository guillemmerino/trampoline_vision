"""Espai reservat per detectar ruptures i contaminació dins d'un fragment.

Analitzarà geometria, moviment, qualitat i aparença disponibles per marcar
trams sospitosos, contactes o caixes mixtes. Aquests avisos podran impedir
actualitzacions d'aparença i alimentar una política explícita de divisió.

No afirmarà un canvi d'actor per una inversió o un únic salt de la caixa.
La detecció i correcció de transferències dins del mateix track_id són
problemes diferents d'unir IDs nous després d'una desaparició.
"""
