"""Validacions petites compartides per configuracions de dominis independents.

No llegeix JSON ni imposa polítiques de tracking o preparació. Cada caller
declara els límits i les claus que admet; els errors són ValueError.
"""

import math


def number_in_range(value: float, name: str, minimum: float, maximum: float) -> None:
    """Exigeix un nombre finit dins del rang tancat, rebutjant booleans i conversions implícites."""
    if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be a finite number in [{minimum}, {maximum}]")


def count_in_range(value: int, name: str, minimum: int, maximum: int) -> None:
    """Valida un recompte enter real; True no es considera un punt ni un fotograma."""
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer in [{minimum}, {maximum}]")


def known_options(value: dict, allowed: set[str], name: str) -> dict:
    """Exigeix un objecte de configuració sense claus desconegudes ni valors implícitament convertits."""
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValueError(f"Invalid or unknown options in {name}")
    return value
