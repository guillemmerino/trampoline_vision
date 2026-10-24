"""Errors d'entrada amb significat propi per al pipeline i la CLI.

Permeten distingir configuració, vídeo i deteccions sense interpretar
el text de l'error. Tots deriven d'InputError perquè la CLI els pugui
presentar com a errors esperats d'ús, amb codi de sortida 2.
"""


class InputError(ValueError):
    """Base dels errors esperats en interpretar o validar una entrada.

    Hereta de ValueError perquè l'entrada no compleix el significat requerit.
    La causa concreta s'afegeix al missatge i es conserva amb raise ... from.
    """


class ManifestError(InputError):
    """El manifest o la configuració no defineixen una entrada interpretable.

    Exemples: ruta inexistent, esquema no suportat o base d'índex ambigua.
    """


class VideoProbeError(InputError):
    """No es poden obtenir dimensions o temps de presentació fiables del vídeo.

    Inclou ffprobe absent, errors de descodificació i línies temporals incoherents.
    """


class DetectionFormatError(InputError):
    """Les deteccions enregistrades incompleixen el format o l'alineació declarats.

    Un JSON malformat o duplicat no s'ha de convertir en una detecció buida.
    """
