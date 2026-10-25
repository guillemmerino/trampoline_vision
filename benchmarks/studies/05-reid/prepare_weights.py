"""Descarrega els pesos públics del protocol i en valida el SHA abans de publicar-los.

No entrena cap model, no envia vídeos i no substitueix fitxers existents.
La càrrega de PyTorch posterior només accepta els bytes fixats al protocol.
"""

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import gdown

from trampoline_vision.infrastructure.artifacts import publish_exclusive


def main():
    """Prepara pesos verificats en una carpeta local de cache amb descàrrega temporal."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol',type=Path,required=True)
    parser.add_argument('--directory',type=Path,required=True)
    args=parser.parse_args()
    protocol=json.loads(args.protocol.read_text(encoding='utf-8'))
    args.directory.mkdir(parents=True,exist_ok=True)
    target=args.directory/protocol['reid_weights']
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest()!=protocol['reid_sha256']:
            raise ValueError('Existing model differs from protocol; refusing replacement')
        print('Existing weights verified',flush=True)
        return
    with tempfile.TemporaryDirectory(prefix='reid-download-',dir=args.directory) as temporary:
        staged=Path(temporary)/target.name
        gdown.download(protocol['reid_source'],str(staged),quiet=False)
        if hashlib.sha256(staged.read_bytes()).hexdigest()!=protocol['reid_sha256']:
            raise ValueError('Downloaded weights differ from protocol')
        publish_exclusive(staged,target)
    print('Published verified weights',target,flush=True)


if __name__=='__main__':
    main()
