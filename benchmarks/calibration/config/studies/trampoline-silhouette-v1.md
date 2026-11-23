# Confiança YOLO i silueta en el manteniment d’IDs

El resultat més consistent als tres vídeos és **considerar totes les
candidates disponibles per mantenir un ID confirmat i aplicar una penalització
suau segons la confiança YOLO**, amb velocitat simple. Guanya set parells
d’anotacions respecte d’abaixar el tall a 0,001 i conserva tots els parells
que el control ja mantenia. El suport de silueta, amb la regla i els pesos
provats, presenta guanys puntuals i regressions. La cerca al voltant de
l’última caixa amb confiança suau té menys contaminació als escenaris
sintètics difícils i queda com a control per al seguiment de la identitat.

## Entrades i variants

El [pla executable](trampoline-silhouette-v1.json) compara 13 variants
en 84 clips simulats (set escenaris, 12 llavors cadascun) i els 2.610
fotogrames dels tres vídeos reals. Els controls del [prototip anterior](trampoline-tracker-prototype-v1.md)
reprodueixen les mètriques originals. Les anotacions i les etiquetes d’actor
s’usen exclusivament per avaluar.

El replay reutilitza les mateixes 31.320 candidates de YOLOv8m a 0,001,
zona central soft i tall de 12. El suport de silueta es recalcula llegint
els píxels originals amb els mateixos temps i fotogrames de fons que al
run de preparació. Es mesura el component dominant com l’arrel quadrada
del producte entre la fracció de la caixa que omple i la fracció del
component que la caixa cobreix. Això conserva la confiança original de
YOLO i evita incorporar la posició a la zona central o el rànquing sencer
com a part del senyal nou. La prova no aplica descriptors d’aparença al
prototip i usa només el tracking de caixes.

En tots els prototips, les caixes fortes (a partir de 0,10) es consideren
primer i fan falta tres observacions fortes i fiables per confirmar un ID.
Els tracks confirmats que queden sense observació passen a una segona
assignació. El control exclou scores inferiors a 0,02 o 0,001. Les
variants noves deixen entrar totes les caixes disponibles en aquesta
passada. En la variant de confiança suau, un score baix augmenta el cost
de manera contínua, fins a 0,09 unitats. La variant amb protecció també
comprova antiguitat, possibles duplicats i marges entre actors i caixes.
La silueta redueix el cost segons el seu suport, amb pesos 0,26 i 0,48.
El pla inclou una variant que conserva la silueta i treu la penalització
de YOLO d’aquesta segona assignació.

Als clips sintètics, el suport és un valor generat amb soroll i solapament
entre actors. L’escenari de primer pla distractor augmenta el suport de
falses candidates i redueix el del gimnasta amb confiança baixa. Aquest
estrès comprova com respon la política a un senyal enganyós. La distribució
del suport és una hipòtesi de la simulació.

## Resultats sobre els tres vídeos

Es compta la continuïtat si dues anotacions visibles consecutives del
mateix gimnasta comparteixen un ID del tracker als extrems. Hi ha 202
parells possibles i 179 instants amb candidata de referència a IoU ≥0,5.
Les referències continuen sent disperses i provisionals.

| Variant | Mateix ID / 202 | Observacions compatibles / 179 | Canvis d’ID entre parells observats als dos extrems |
| --- | ---: | ---: | ---: |
| BoT-SORT enregistrat | 109 | 149 | 10 |
| Última caixa, tall 0,001 | 119 | 168 | 25 |
| Última caixa, YOLO suau | 112 | 167 | 31 |
| Velocitat, tall 0,02 | 100 | 150 | 16 |
| Velocitat, tall 0,001 | 127 | 167 | 15 |
| **Velocitat, YOLO suau** | **134** | **169** | 12 |
| Velocitat, YOLO suau i protecció d’ambigüitat | 114 | 161 | 20 |
| Velocitat, mateixa protecció i silueta | 114 | 160 | 19 |
| Velocitat, protecció i silueta sense penalització YOLO | 120 | 162 | 16 |

El control de tall 0,001 i la confiança suau amb velocitat donen,
respectivament, 49→52, 39→41 i 39→41 parells per vídeo. En el contrast
aparellat hi ha set guanys i cap pèrdua. Amb el criteri geomètric permissiu
el recompte també puja de 140 a 144. Respecte de BoT-SORT, la variant
guanya 34 parells i en perd nou. A les 15 àncores del gimnasta amb rol
revisat provisionalment, hi ha observació en 12 i cap canvi cap a un
altre actor entre les àncores, davant de tres canvis amb BoT-SORT i un
amb velocitat i tall 0,001. El nombre d’àncores és massa petit per
estimar una taxa real de transferències.

Les caixes d’AGE2 als frames 525, 527 i 531 obtenen suport de silueta
0,671, 0,417 i 0,548. La velocitat amb YOLO suau les associa totes tres
al mateix ID. Amb el tall 0,001, la tercera té un altre ID. Amb la política
de protecció i silueta s’observa la primera i queden pendents les altres
dues. Aquests tres punts revisats mostren que un suport alt ajuda a
localitzar una caixa, però la decisió temporal també depèn de les
altres candidates i de l’estat acumulat del track.

## Simulació de contaminació d’identitat

Cada columna resumeix 12 seqüències amb 1.848 fotogrames amb candidata
del gimnasta. La contaminació compta cada assignació d’un ID que ja
havia seguit el gimnasta a un altre actor o a una caixa mixta. Un sol
intercanvi persistent pot acumular moltes assignacions. Els controls
de BoT-SORT enregistrats estan disponibles per als vídeos reals.

| Variant | Observacions contaminades, escenari combinat | Observacions contaminades, primer pla distractor |
| --- | ---: | ---: |
| Última caixa, tall 0,001 | 150 | 268 |
| Última caixa, YOLO suau | **121** | 188 |
| Última caixa, YOLO suau i protecció | 177 | 182 |
| Última caixa, mateixa protecció i silueta | 185 | **137** |
| Última caixa, mateixa protecció i silueta amb pes 0,48 | 197 | 194 |
| Velocitat, tall 0,001 | 945 | 963 |
| Velocitat, YOLO suau | 923 | 943 |
| Velocitat, YOLO suau i protecció | 922 | 930 |
| Velocitat, mateixa protecció i silueta | 946 | 1.092 |

La protecció de l’última caixa redueix els canvis d’actor de 29 a 20
a l’escenari combinat, però augmenta la contaminació de 121 a 177.
Hi ha menys transferències i algunes duren més. Amb desplaçament de
càmera, afegir silueta a aquesta mateixa cerca baixa de 271 a 193
observacions contaminades. El resultat depèn del predictor i de la
qualitat del primer pla.

La continuïtat real afavoreix **velocitat amb YOLO suau**. La simulació
adverteix que pot prolongar un error en contactes. Cal contrastar-la en
vídeos reservats amb la darrera caixa i YOLO suau, mesurant també la
durada dels intercanvis. La silueta queda com a senyal experimental amb
resultats mixtos. Les referències actuals només permeten comprovar la
identitat als extrems i en les àncores visuals disponibles.

## Reproducció

Des de l’arrel, amb la imatge local de calibratge i els runs congelats.

```bash
docker run --rm --network none --entrypoint python \
  --user "$(id -u):$(id -g)" \
  -e PYTHONPATH=/workspace/src:/workspace -e PYTHONDONTWRITEBYTECODE=1 \
  -e OPENBLAS_NUM_THREADS=1 \
  --mount "type=bind,src=$PWD,dst=/workspace,readonly" \
  --mount "type=bind,src=$PWD/runs/calibration,dst=/results" \
  -w /workspace trampoline-vision:calibration-gpu-v1 \
  -m benchmarks.calibration.tools.run_trampoline_tracker_prototype \
  --plan benchmarks/calibration/config/studies/trampoline-silhouette-v1.json \
  --output /results/trampoline-silhouette-repeat
```

L’execució verificada és a `runs/calibration/trampoline-silhouette-v1/`
i ha trigat 64 s. `summary.json` desa les mètriques per escenari i vídeo.
`real-silhouette.jsonl.gz` conserva el suport, l’àrea ocupada, la cobertura
del component i la confiança original, per candidata. Les assignacions són
a `real-traces.jsonl.gz` i els parells a `real-pairs.jsonl.gz`.
`inputs.json` i `completed.json` vinculen codi, configuració, fonts i
sortides. S’han comprovat els hashes, els 84 clips per variant, la cobertura
del replay i 14 proves unitàries.
