# Configuració compartida i estudis en curs

- `corpus.json`: inventari portable de vídeos i models, amb hashes i metadades.
  Tenir 94 vídeos al corpus no implica executar-los tots.
- [studies/](studies/README.md): plans nous en curs, quan n’hi hagi.

Els plans i matrius tancats de detecció, preparació i zona s’han mogut a
[l’arxiu](../archive/detection-preparation-v1/README.md). No són defaults del pipeline.
Les constants de `engine/paths.py` resolen els plans històrics dels executors
que els reprodueixen; una prova nova ha de declarar el seu pla explícitament.

Els perfils de producció del detector/preparació/tracker, quan pertoqui,
viuen a [configs/ del projecte](../../../configs/), fora del banc experimental.
