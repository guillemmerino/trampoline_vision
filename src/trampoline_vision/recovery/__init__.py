"""Preparació de reconstrucció offline després del tracking complet.

pipeline i tracklets construeixen fragments observats i buits amb evidència
predita, amb configuració activable/desactivable i invariants verificades.
No s'uneixen tracks ni s'assigna actor_id en aquest primer increment.
motion, appearance, coherence i association són etapes futures per passar
de fragments auditables a una reconstrucció d'actors validada.
Importar el paquet no carrega models, trackers ni dependències numèriques.
"""
