"""Entrada de python -m trampoline_vision.

Delega a la mateixa funció main que la comanda instal·lada trampoline-vision.
El guard __name__ evita executar la CLI quan s'importa el mòdul i SystemExit
transmet el codi retornat al terminal o al contenidor.
"""

from trampoline_vision.interfaces.cli.main import main

if __name__ == "__main__":
    raise SystemExit(main())
