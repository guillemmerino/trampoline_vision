"""Espai reservat per associar deteccions i conservar identitats.

Consumirà TrackingFrame inclosos els fotogrames buits i generarà
TrackingFrameResult. Els contractes són a contracts.tracking. El primer
backend escollit és OC-SORT de trackers 2.6.1, però encara no hi ha adaptador,
predictor propi ni assignació de track_id implementats en aquest domini.
"""
