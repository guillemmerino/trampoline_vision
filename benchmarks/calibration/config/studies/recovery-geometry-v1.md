# Primera prova de recovery geomètric

El perfil `global-geometry-v1` empata amb el tracker base a les àncores
del gimnasta, **33 de 45 parells**, amb quatre guanys i quatre pèrdues.
En dos dels cinc buits amb canvi d’ID, els extrems del gimnasta cauen
a la mateixa cadena proposada. En el buit seleccionat on el tracker ja
conservava l’ID, la cadena del recuperador els separa. Hi ha quatre
cadenes que contenen àncores del gimnasta i d’algun altre actor.

## Execució i criteris

El [pla](recovery-geometry-v1.json) fixa el perfil, les traces i l’elecció
d’extrems per als sis buits i sis transferències del
[catàleg provisional](recovery-case-catalog-v1.md). S’han auditat els
2.610 fotogrames dels tres vídeos complets amb el perfil geomètric
existent. L’auditoria opera sobre el vídeo complet i les àncores
s’utilitzen a posteriori per contrastar les propostes.

L’adaptador agafa les 31.320 candidates preparades, la geometria i la
procedència del replay, i les combina amb les 15.103 observacions i els
7.496 estats predits de `velocity_soft_yolo`. La traça experimental
només publica els IDs de predicció, de manera que els estats `lost`
es representen sense caixa. `finished` es deriva del primer fotograma
on un ID públic deixa d’aparèixer. L’adaptador elimina els motius
d’exclusió del tracker usat per enregistrar les candidates, i el
lector de producció valida el vídeo, els temps i el cicle dels IDs.
S’ha comprovat la paritat de candidates, observacions i IDs predits
fotograma a fotograma.

Per a cada parell de fotogrames amb àncora del gimnasta, consecutius
dins la finestra, es comprova si alguna combinació de candidates
útils comparteix ID a la traça original o cadena a l’auditoria.
Els 45 parells són extrems observats amb rols provisionals. Un parell
pot coincidir als extrems i tenir problemes entremig o fora de la finestra.
Per això es comproven també les transferències i les cadenes amb
àncores d’actors incompatibles, encara que quedin en finestres diferents.
Els recomptes descriuen aquesta mostra escollida de casos.

## Sis buits

| Vídeo i àncores | IDs del tracker | Resultat de l’auditoria |
| --- | --- | --- |
| AGE1, 495→510 | 174→191 | El solver tria altres unions. |
| AGE1, 765→778 | 253→259 | Els fragments solapen. El 253 inclou observacions de l’assistent. |
| AGE2, 525→531 | 92→92 | El solver separa els extrems que el tracker mantenia amb el mateix ID. |
| AGE2, 967→980 | 198→222 | Unió directa proposada amb cost 0,088. |
| AGE3, 99→121 | 26→60 | Mateixa cadena a través d’un fragment intermedi del 26. |
| AGE3, 440→458 | 117→145 | El solver tria altres unions. |

Els quatre guanys del recompte general inclouen aquests dos buits, més
195→198 a AGE2 i 64→82 a AGE3. Les quatre pèrdues apareixen amb els IDs
36, 92 i 198 d’AGE2 i 82 d’AGE3. Als sis controls de continuïtat es
passa de 18/18 parells amb el tracker a 16/18 amb l’auditoria.

## Transferències

En quatre de les sis transferències, els dos extrems assenyalats
queden en cadenes diferents després de l’associació. En aquests
quatre casos ja existia una interrupció d’observació entre els
extrems, que la política de fragmentació podia aprofitar.

- A AGE1, l’ID 189 conté el gimnasta al 713 i l’assistent al 722
  dins del mateix fragment (713–728). A AGE3 passa el mateix amb
  l’ID 0 entre el 60 i el 65 (fragment 45–110).
- Els avisos de discontinuïtat interna apareixen dins del tram revisat
  en una de les sis transferències. Són els avisos als fotogrames 706
  i 707 d’AGE2 per a l’ID 125. Les altres cinc transicions no
  generen avisos per al mateix ID dins del seu interval de cerca.
- Quatre cadenes contenen àncores del gimnasta i d’altres actors.
  En tres d’aquestes, l’associació entre fragments posa també junts
  gimnasta i un altre actor amb IDs originals diferents. A AGE2,
  per exemple, el 147 segueix el gimnasta al 740 i queda en la
  mateixa cadena que el 195 quan segueix l’assistent al 867.
  Això passa encara que les dues àncores escollides per comprovar
  la transferència interna del 195 quedin en cadenes diferents.

El perfil és una base per contrastar variants. Amb aquestes àncores,
els enllaços útils compensen les pèrdues en el recompte d’extrems, i
la contaminació encara arriba a les cadenes. La prova següent pot
comprovar si aïllar trams contaminats i protegir continuïtats fiables
evita aquests conflictes abans de canviar el cost d’unió.

## Reproducció

Des de l’arrel, amb el corpus local `data/calibration-v1` i els runs
congelats `trampoline-silhouette-v1` i `identity-continuity-v1`.

```bash
docker run --rm --network none --entrypoint python \
  --user "$(id -u):$(id -g)" \
  -e PYTHONPATH=/workspace/src:/workspace -e PYTHONDONTWRITEBYTECODE=1 \
  --mount "type=bind,src=$PWD,dst=/workspace,readonly" \
  --mount "type=bind,src=$PWD/runs/calibration,dst=/results" \
  -w /workspace trampoline-vision:calibration-gpu-v1 \
  -m benchmarks.calibration.tools.run_recovery_geometry \
  --plan benchmarks/calibration/config/studies/recovery-geometry-v1.json \
  --output /results/recovery-geometry-v1-repeat
```

En mode CPU, la passada verificada ha trigat uns 12 s. Les sortides
són a `runs/calibration/recovery-geometry-v1-reviewed/`. `summary.json`
recull àncores, fragments, camins i enllaços directes per cas. Cada
subdirectori de vídeo conté la traça canònica, els límits dels fragments,
l’informe de producció i el JSONL complet de propostes i rebutjos.
`completed.json` fixa les empremtes dels 16 artefactes. Per a la
revisió visual, els mateixos `window_id` permeten obrir els MP4
del catàleg existent. La passada ha estat una auditoria i
els informes registren `applied: false`.
