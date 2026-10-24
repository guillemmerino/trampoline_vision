# 0005. OC-SORT instal·lable i frontera de tracking

- Data: 24/10/2026.
- Estat: accepted per al primer baseline; eficàcia sobre trampolí pendent de mesura.

## Context

La càmera és fixa, hi ha múltiples actors i el gimnasta pot ser petit, invertir-se
i perdre articulacions. Disposem d'OpenPose enregistrat, però no d'un corpus
per entrenar. Necessitem provar un tracker existent sense lligar els dominis
posteriors a una llibreria ni perdre evidència feble en preparar les dades.

## Decisió

Adoptar inicialment `OCSORTTracker` de `trackers==2.6.1` com a dependència
opcional `tracking`, amb llicència Apache 2.0 i entrada de caixes externes.
És una implementació pròpia de Roboflow de l'algoritme, no entrenament nostre.
L'adaptador s'implementarà en un increment posterior.

Definir la frontera a `contracts/tracking.py`, independent de la biblioteca:
font original, candidats preparats amb mesura opcional, estat de trajectòria
i resultat amb assignacions traçables. Deduplicació i estimació de caixes
corresponen a `preparation`; identitats temporals corresponen a `tracking`;
selecció del gimnasta correspon a `subjects`.

## Conseqüències

- La biblioteca usa CPU i no exigeix pesos per executar OC-SORT sobre caixes.
- Les transitives inclouen NumPy >=2; s'aïllen del projecte antic i del nucli.
- Els timestamps reals s'enviaran explícitament, també per fotogrames buits.
- La confiança de pose no es presenta com confiança calibrada de detector.
- OC-SORT 2.6.1 no té associació diferenciada de baixa confiança com ByteTrack.
  No es promet aquesta capacitat ni robustesa sobre trampolí abans de provar-la.
- Una pose sense caixa justificada es conserva, però no entra com a mesura
  rectangular a aquest backend. La seva utilitat temporal s'avaluarà després.
- Un extra fixat no substitueix un lock de transitives ni l'inventari de llicències.
- La màquina d'estats, el ledger d'identitats i la validació de seqüència encara
  no estan implementats. Els contractes només validen coherència d'un instant.

## Alternatives

El repositori original d'OC-SORT és la referència de l'algoritme, però conté
també el recorregut de detecció i eines de recerca; preferim una distribució
instal·lable amb API pública per a caixes. No en copiem el tracker al projecte.

ByteTrack queda com a comparació especialment rellevant per evidència feble.
BoT-SORT no aporta ara una necessitat prioritària de compensació de càmera.
No s'exclou cap algoritme futur: el contracte no conté objectes `sv.Detections`.

API, límits, dependències, fonts i verificació a la
[guia 19](../19-tracking-contracts-and-backend.md).
