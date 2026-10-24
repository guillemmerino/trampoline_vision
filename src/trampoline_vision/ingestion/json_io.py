"""Lectura JSON compartida per manifests, configuracions i deteccions.

Rebutja claus repetides, literals NaN/Infinity i arrels que no siguin
objectes. Així s'evita acceptar interpretacions ambigües abans de validar
els camps de cada format. Les funcions no coneixen OpenPose ni el vídeo.
"""

import json
from pathlib import Path
from trampoline_vision.ingestion.errors import InputError


def _pairs(pairs: list[tuple[str, object]]) -> dict:
    """Reconstrueix un objecte JSON i rebutja una clau si ja ha aparegut.

    json.loads passa aquí les parelles abans de convertir-les a dict. Un
    dict normal conservaria només l'últim valor i amagaria l'ambigüitat.
    """
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _constant(value: str) -> None:
    """Rebutja els literals no finits que json.loads pot admetre per defecte.

    És el callback parse_constant; sempre genera ValueError per NaN o
    Infinity. Els camps numèrics també es validen després al lector específic.
    """
    raise ValueError(f"Non-finite JSON number: {value}")


def parse_json(text: str, source: str) -> dict:
    """Interpreta text JSON com a objecte i contextualitza els errors amb source.

    Retorna el diccionari sense transformar-ne els camps. source és només
    una etiqueta de diagnòstic, com el nom d'un membre ZIP. Un error de
    sintaxi, claus repetides o tipus d'arrel genera InputError.
    """
    try:
        obj = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, RecursionError) as exc:
        raise InputError(f"Invalid JSON in {source}: {exc}") from exc
    if not isinstance(obj, dict):
        raise InputError(f"Expected a JSON object in {source}")
    return obj


def read_json(path: Path) -> dict:
    """Llegeix un fitxer UTF-8 i aplica la interpretació JSON estricta.

    utf-8-sig admet també un BOM inicial. Els errors de disc o de codificació
    es transformen en InputError amb la ruta; no es creen ni modifiquen fitxers.
    """
    try:
        return parse_json(path.read_text(encoding="utf-8-sig"), str(path))
    except (OSError, UnicodeError) as exc:
        raise InputError(f"Cannot read {path}: {exc}") from exc
