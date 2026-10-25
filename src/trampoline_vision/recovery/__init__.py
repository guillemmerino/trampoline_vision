"""Reconstrucció d'identitats d'actor a partir d'un tracking complet.

Estat: estructura reservada, sense algoritme ni integració executable.
El recorregut previst és offline i global: fragments, evidències, enllaços
compatibles, resolució conjunta i validació de trajectòries. Les finestres
temporals limiten els enllaços; no divideixen el vídeo en execucions aïllades.

track_id conserva la identitat del tracker; fragment_id identifica un tram
analitzat; actor_id relacionarà fragments compatibles. Es mantindran les
observacions i prediccions originals i l'opció de deixar unions pendents.
Importar aquest paquet no executa inferència ni carrega dependències opcionals.
La guia docs/28-recovery-package-design.md descriu el pla de construcció.
"""
