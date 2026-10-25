"""Espai reservat per exportar i visualitzar reconstruccions d'actor.

Publicarà mapping de fragments/actors, decisions amb costos i alternatives,
intervals ambigus i resum de procedència/configuració. L'overlay futur podrà
mostrar actor_id i track_id conjuntament amb evidència observada/predita.

Els artefactes tindran esquema i destinacions propis; no substituiran el
JSONL de tracking ni fabricaran observacions per omplir desaparicions.
No hi ha encara serialitzadors, renderer ni artefactes nous en execució.
"""
