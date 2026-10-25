"""Espai reservat per als contractes immutables de reconstrucció.

Definirà fragments, enllaços candidats, evidències, decisions i trajectòries
d'actor amb procedència. track_id, fragment_id i actor_id tindran àmbits
explícits dins d'un vídeo/run; es conservaran les referències als candidats.

Els resultats distingiran unions proposades, acceptades, rebutjades i pendents
i evidència observada/predita. No es reemplaçarà TrackingFrameResult ni es
reescriuran retroactivament les decisions originals del tracker.
Els tipus i invariants encara s'han de definir; no hi ha API implementada.
"""
