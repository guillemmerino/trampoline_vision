# 17. Visualització de deteccions: pas 3

## Finalitat i abast

`visualize` dibuixa les observacions BODY_25 sobre les imatges del vídeo original i exporta un
MP4 i un informe JSON. Reutilitza manifest, vídeo i lector OpenPose; no executa inferència,
deduplicació, tracking, selecció de gimnasta, segmentació o puntuació.

La revisió serveix per comprovar visualment coordenades i correspondència temporal, i per
identificar soroll, duplicats i fallades que els passos posteriors hauran de tractar. Una exportació
correcta tècnicament no demostra que l'esquelet sigui anatòmicament correcte.

## Comandes Docker CPU

Des de la carpeta del projecte, amb `runs/` existent:

```powershell
docker compose build replay
docker compose run --rm replay visualize --config configs/pipelines/visualize-openpose.json --start 0 --end 3 --view compare --output runs/review-short.mp4
docker compose run --rm replay visualize --config configs/pipelines/visualize-openpose.json --output runs/review-full.mp4
docker compose run --rm replay visualize --config configs/pipelines/visualize-openpose.json --start 14 --end 17 --view compare --output runs/review-flight.mp4
```

El primer recorregut compara totes les observacions amb el filtre en un interval curt. El segon
genera el clip complet filtrat. Els informes són `review-short.json` i `review-full.json`.
Els noms existents es rebutgen; utilitzar-ne de nous per repetir una prova.

Es pot passar `--manifest` en lloc de `--config`. La configuració ha de ser la de visualització,
no `inspect-openpose.json` ni l'exemple de pipeline complet design-only.

## Vistes i filtres

| Opció | Comportament |
| --- | --- |
| `--view all` | Mostra punts observats dins la imatge amb confiança positiva, sense aplicar els llindars de la vista filtrada. |
| `--view filtered` | Aplica confiança mínima per punt i mínim de punts visibles per dibuixar una detecció. |
| `--view compare` | Situa all a l'esquerra i filtered a la dreta, a la mateixa escala i sobre el mateix fotograma. |
| `--min-confidence` | Llindar visual dins de [0,1]; el valor inicial és 0.25. |
| `--min-visible-points` | Nombre de punts que superen el filtre i són dins del marc; valor inicial 6. |
| `--labels` / `--no-labels` | Mostra o amaga IDs de detecció. |
| `--start` / `--end` | Interval de temps del vídeo original; s'escullen inicis de fotograma dins de `[start,end)`. |
| `--report` | Ruta opcional de l'informe; per defecte mateixa base que el MP4 amb extensió `.json`. |

Les opcions de terminal prevalen sobre les d'estil del fitxer. Els llindars inicials són una ajuda
de revisió, no una política adoptada de filtratge del tracker. Poden amagar un gimnasta parcialment
detectat; la comparació amb all permet observar aquest efecte. Els punts absents o fora de marc no
s'inventen ni es projecten al marge. Les connexions requereixen els dos extrems visibles.

## Identificadors, colors i geometria

Les etiquetes són `frame_index:posició`, amb posició començant a zero. Els colors distingeixen
propostes dins d'un fotograma. No representen identitats persistents i poden canviar entre instants.
No s'han d'interpretar com a seguiment.

La capçalera ocupa 64 píxels addicionals per sobre de la imatge, sense tapar l'atleta. L'escala
és 1:1. Un panell únic té origen `(0,64)` i el segon, en comparació, `(amplada_original,64)`.
Si cal, s'afegeix un píxel de padding al final per obtenir dimensions parelles per a H.264.
Aquest layout es declara a l'informe; no modifica les coordenades dels contractes.

El diagnòstic s'exporta sense àudio, amb H.264/yuv420p. L'original no es modifica.

## Temps i verificació automàtica

PyAV descodifica el vídeo a CPU. Es contrasta índex, dimensions i temps amb el `VideoAsset`
obtingut per ffprobe. El MP4 exportat comença a zero; la capçalera i l'informe conserven els temps
i índexs originals del tram. Els intervals variables es conserven amb PTS i durades explícites.

Després de codificar, ffprobe torna a llegir la sortida. S'exigeix recompte de fotogrames exacte,
dimensions del layout i error màxim de temps/durada de 0.0001 s. També es manté el fotograma sense
deteccions i es distingeix un JSON absent d'un JSON amb `people: []`.

`visual_alignment_status: pending_human_review` continua a l'informe fins que una persona revisi
les imatges. La verificació de PTS no demostra que els JSON ja enregistrats estiguin semànticament
alineats amb l'atleta. La configuració no inclou una correcció temporal automàtica oculta.

## Informe i publicació

L'informe desa estil efectiu, interval demanat i interval real, fonts, versions de dependències,
layout, recomptes per vista i fotograma, avisos i verificació de la recodificació. El temps d'execució
inclou codificació i verificació, però no el primer sondeig del vídeo fet per la CLI.

Es generen temporals abans de publicar MP4 i informe. No se sobreescriu cap fitxer existent.
Els dos artefactes no són una transacció conjunta: l'informe es publica al final. Un error de JSON
o codificació no publica un vídeo parcial com si el recorregut hagués acabat.

## Dependències i proves

El nucli i `inspect` continuen sense dependències Python d'execució. L'extra `visualization`
afegeix Pillow i PyAV, carregats sota demanda; Docker CPU els incorpora per executar els dos passos.
PyAV 16 es manté per compatibilitat amb Python 3.10/3.11. Les versions resoltes es desen a l'informe;
les dependències encara no estan bloquejades amb un lockfile complet.

Les proves comproven píxels a coordenades conegudes, filtres que no alteren les dades, buits,
primer/últim fotograma, intervals parcials, temps variables i errors abans de publicar. Les proves
de vídeo real són sintètiques i no substitueixen la revisió visual del cas de trampolí.

Referències: [Pillow ImageDraw](https://pillow.readthedocs.io/en/stable/reference/ImageDraw.html),
[temps de PyAV](https://pyav.org/docs/stable/api/time.html) i
[compatibilitat de PyAV 16](https://pypi.org/project/av/16.0.1/).
