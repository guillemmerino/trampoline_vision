"""Espai reservat per a la configuració validada de reconstrucció.

Definirà activació, mode audit/apply, execució global, estratègia i referència
opcional al model d'aparença. També validarà els paràmetres experimentals
de temps, compatibilitat, costos i ambigüitat, amb unitats explícites.

No llegirà fitxers ni importarà models o solvers; la resolució de rutes serà
a ingestion.recovery_config. Els exemples actuals són design-only i no
constitueixen encara un esquema executable ni defaults calibrats.
"""
