# Comparació de la zona comuna centrada

La prova compara tres variants del mateix codi de `src/preparation`:

| Variant | Zona | Mode | Pregunta |
| --- | --- | --- | --- |
| `previous_hard` | Antiga, segons el panell de càmera | `hard` | Referència de treball anterior. |
| `previous_soft` | La mateixa zona antiga | `soft` | Què canvia en retirar l’exclusió espacial? |
| `centered_soft` | `[0.06, 0.25, 0.94, 0.93]`, comuna | `soft` | Què canvia en substituir la zona particular per una preferència central? |

Es mantenen el detector, totes les polítiques d’agrupament, la contenció,
el fons medià i el pressupost de 12 caixes. Només varien zona i mode.
La comparació `previous_hard → previous_soft` aïlla el mode;
`previous_soft → centered_soft` aïlla la geometria de la zona.
Les zones antigues corresponen al panell esquerre `[0, 0.69]` o dret
`[0.30, 1]`, amb els marges `[0.06, 0.25, 0.94, 0.93]` aplicats dins
del panell. Això dona `[0.0414, 0.25, 0.6486, 0.93]` a l’esquerra i
`[0.342, 0.25, 0.958, 0.93]` a la dreta. El pla versionat conserva
els dos clips esquerres de l’estudi de 18 vídeos; no els confon amb els
tres clips esquerres de la prova contínua posterior de 12 vídeos.

## Execució

Des de l’arrel del repositori:

```bash
bash benchmarks/calibration/commands/run-zone-comparison.sh
```

Per comprovar només els inputs, sense crear resultats:

```bash
bash benchmarks/calibration/commands/run-zone-comparison.sh --dry-run
```

També s’exposa com `python3 -m benchmarks.calibration study zones`.
Requereix Docker, la imatge `trampoline-vision:calibration-gpu-v1`, el paquet
local `data/calibration-v1` i `runs/calibration/expanded-localization-v1/human-review`
amb `bundle.json` i `review-state.json`. No necessita GPU, CUDA ni pesos de models.
El wrapper assumeix el reconeixement explícit de referències provisionals amb
`--allow-provisional-references`; no les converteix en validació humana.

Per defecte processa els **18 vídeos i 1.440 fotogrames anotats** del
[pla](../config/iterations/06-zone-comparison.json). Les deteccions de
YOLOv8m a confiança 0,001/NMS 0,7 es reutilitzen del bundle verificat contra
les decisions humanes. **No repeteix YOLO ni executa cap tracker.**
Es descodifiquen els clips per construir el fons i arribar als instants
anotats; les tres variants de preparació només s’executen en aquests instants.
No és una avaluació de cada fotograma dels vídeos complets ni genera MP4.

La destinació és `runs/calibration/zone-comparison-v1`. Si ja existeix,
la comanda s’atura sense sobreescriure-la. Es pot triar una altra amb
`--output /results/zone-comparison-v2` (ruta interior de Docker).
`CALIBRATION_DATASET`, `CALIBRATION_RESULTS`, `CALIBRATION_IMAGE` i
`CALIBRATION_CPUS` permeten adaptar les rutes i els recursos del wrapper.

## Resultats per revisar en una iteració independent

- `index.html`: totals de les variants i enllaços a les galeries per vídeo.
- `<vídeo>/index.html`: mateix fotograma amb les tres seleccions. Verd:
  candidates; blau: zona; groc: referència IA; magenta: caixes humanes.
- `summary.json`: recomptes per vídeo, per partició i globals; denominadors,
  guanys i pèrdues aparellats (`paired_changes`), temps i RSS màxim.
- `frames.jsonl.gz`: tots els originals, referències, geometria i procedència
  de les candidates, puntuacions de rànquing, decisions de selecció i mètriques.
- `discrepancies.jsonl`: casos amb canvi de cobertura, IoU o excés d’àrea,
  i casos on la variant central queda per sota del 90% de cobertura.
  Si el detector cru ja quedava per sota, es marca separadament.
- `inputs.json`: pla, configuració, detector, estat provisional i hashes
  dels inputs i del codi. `decisions-snapshot.json` congela la revisió humana.
- `completed.json`: es publica al final, amb hashes dels principals registres.
  Una carpeta sense aquest marcador pot correspondre a una execució interrompuda.

Les mètriques distingeixen `ai_reference`, `human_useful_detection` i
`human_reference`. La primera conserva l’anotació provisional. La segona
mesura la conservació de la caixa YOLO que l’usuari va considerar útil o
parcial; no és una referència independent de cos sencer. La tercera usa
només geometria humana explícitament aprovada o corregida, si n’hi ha.
Cada subconjunt manté el seu denominador; els instants exclosos per l’IA
no es tracten com a negatius de detecció.

Cobertura 90%/95%, IoU 0,5 i límit diagnòstic d’àrea 4× serveixen per
trobar discrepàncies. **No equivalen a una pèrdua confirmada del gimnasta**:
una caixa parcial pot ser útil segons el criteri acceptat. Cal inspeccionar
especialment les pèrdues de `previous_soft → centered_soft`, les caixes humanes
deixades fora i els salts alts o desplaçaments laterals. El temps total
inclou preflight, lectura, fons, preparacions i exportació JSONL/JPG/HTML;
el temps per variant només inclou preparació amb auditoria.

## Responsabilitats del codi

`tools/compare_zones.py` adapta el bundle als contractes de producció i
orquestra l’avaluació. `previous_zone` reprodueix les zones antigues;
`variants` deriva tres configuracions sense tocar els llindars;
`resolve` verifica pla, mostres, SHA-256 dels vídeos i decisions humanes;
`targets_for` separa els tipus de referència; `metrics` calcula geometria;
`discrepancies` assenyala casos de revisió; `_card` i `_html` generen la
galeria; `run` publica els registres i `main` exposa els arguments.
La selecció de caixes continua sent responsabilitat de
`RepresentativeBoxPreparer.prepare_with_audit`, no d’aquest adaptador.
`commands/run-zone-comparison.sh` només configura el contenidor CPU;
no instal·la dependències ni descarrega dades.

## Resultat de l’execució revisada

La prova ha finalitzat amb els 18 clips i 1.440 mostres. S’han verificat els
hashes de finalització i del codi i s’han recalculat les mètriques dels registres.
L’[informe de revisió](../../../../../runs/calibration/zone-comparison-v1/REVIEW.md)
conté la taula per vídeo i 13 imatges reals inspeccionades per l’agent.

| Diagnòstic | Antiga hard | Antiga soft | Central soft |
| --- | ---: | ---: | ---: |
| Cobertura IA ≥90% | 1078/1267 | 1078/1267 | 1077/1267 |
| Cobertura IA ≥90%, àrea≤4× | 817/1267 | 817/1267 | 817/1267 |
| Caixa útil validada, cobertura ≥95% | 56/56 | 56/56 | 56/56 |
| Referència humana, cobertura ≥90% | 52/55 | 52/55 | 52/55 |

La pèrdua addicional al 90% és AGE1 002837 frame1262: una caixa ampla passa
de la posició 12 a quedar fora amb 12 seleccionades. La cobertura de referència
baixa de 96,23% a 85,45%, però la inspecció mostra el gimnasta encara localitzat,
amb menys cobertura dels braços alçats. No és una exclusió directa per zona.
Dos altres fotogrames canvien només el diagnòstic del 95%: AGE1 001814 frame296
millora i frame650 empitjora, amb candidats que continuen localitzant el gimnasta.

Dels 192 fotogrames marcats, 189 ja quedaven per sota del 90% amb la zona antiga,
un és el canvi nou i dos només canvien el llindar del 95%. No són 192 pèrdues
noves. Hi ha problemes previs de blur i fragments; el frame97 d’AGE3 001351
continua sense una localització útil clara del gimnasta, ja des de YOLO.

Recomanació de la revisió: mantenir la zona comuna soft com a configuració de
treball en aquesta mostra, sense atribuir-li detecció universal ni generalització
entre escenaris. No s’han canviat els paràmetres ni repetit inferència o tracking.
Temps total: 167,37 s amb lectura i exportació JPG/HTML, sense MP4; RAM màxima
429,1 MiB; preparació central amb auditoria 25,08 ms per fotograma en aquesta
execució. Les observacions visuals de l’agent no són validació humana nova.
