"""Publicació d'artefactes binaris o de text sense sobreescriure inputs existents."""

from pathlib import Path
import shutil


def publish_exclusive(staged: Path, destination: Path) -> None:
    """Copia bytes a un fitxer nou, netejant la còpia pròpia si l'operació falla.

    El mode xb reserva el nom de manera exclusiva. No és una transacció entre
    diversos artefactes ni una garantia contra una interrupció del procés.
    """
    created = False
    try:
        with destination.open("xb") as target:
            created = True
            with staged.open("rb") as source:
                shutil.copyfileobj(source, target)
    except Exception:
        if created:
            destination.unlink(missing_ok=True)
        raise
