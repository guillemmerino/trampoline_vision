"""Espai reservat per llegir i resoldre configuracions de recovery.

Llegirà perfils versionats, resoldrà cada ruta respecte del fitxer declarant
i delegarà la validació de valors a recovery.config. Rebutjarà claus alienes,
versions no implementades i opcions d'aparença incompatibles.

Els exemples 0.1-draft són només disseny. Aquest mòdul no els consumeix encara
i no s'ha afegit recovery_config al loader actual del pipeline executable.
"""
