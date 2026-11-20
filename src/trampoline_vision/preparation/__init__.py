"""Preparació de deteccions abans del seguiment.

pipeline.prepare_frame/prepare_frames produeixen TrackingFrame. config
defineix polítiques; boxes agrupa caixes semblants i relaciona contencions
ambigües, amb originals intactes; pose calcula extensions justificades i deduplication
agrupa propostes compatibles del mateix instant si s'activa expressament.
El perfil representatiu opcional usa píxels i un fons fix abans del tracking.
No es transformen rotacions ni es fusionen punts; les coordenades d'entrada
ja han de ser les originals. El seguiment temporal correspon a tracking;
aquest paquet no assigna identitats persistents ni reconstrueix esquelets.
"""
