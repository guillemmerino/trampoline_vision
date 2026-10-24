"""Preparació de deteccions abans del seguiment, sense dependències visuals.

pipeline.prepare_frame/prepare_frames produeixen TrackingFrame. config
defineix polítiques; pose calcula extensions justificades i deduplication
agrupa propostes compatibles del mateix instant si s'activa expressament.
No es transformen rotacions ni es fusionen punts; les coordenades d'entrada
ja han de ser les originals. El seguiment temporal encara és una etapa futura.
"""
