# Estat de l’estudi

## Detector

YOLOv8m amb **0,001 principal**, **0,002 control**, NMS 0,7, imgsz 1280,
resize 1,5 i max_det 300. Són paràmetres experimentals del banc; no s’han
substituït els defaults de l’aplicació.

La prova ampliada va completar 36 passades sobre 18 vídeos. Amb les referències
d’IA originals, 0,001 tenia caixa compatible en 1.204/1.267 instants visibles;
0,002, en 1.185/1.267. Hi havia 173 exclusions. Són xifres històriques sobre
mostres, abans de les correccions humanes; no una mesura de tot el vídeo.

[Revisió del resultat ampliat](../../../runs/calibration/expanded-localization-v1/assessment/ASSESSMENT.md).

## Referències i revisió humana

La revisió està en curs a [localhost:8766](http://localhost:8766/).
El seu fitxer de treball és
`runs/calibration/expanded-localization-v1/human-review/review-state.json`.
No es mou amb el codi i la seva revisió pot continuar augmentant.

La primera lectura parcial, fixada a la revisió 212, va trobar deteccions útils
en diversos instants que abans quedaven exclosos i caixes suficients que l’IoU
no acceptava. També hi ha fragments útils i solapaments amb assistents.
[Interpretació parcial](../../../runs/calibration/expanded-localization-v1/human-assessment-r212/INTERPRETATION.md).

[Ús de la revisió humana i revaloració](HUMAN_REVIEW.md).

## Proves existents

| Pla a `config/iterations/` | Abast | Estat |
| --- | --- | --- |
| `01-threshold-robustness.json` | 3 vídeos, 4 confiances, 4 trackers | Executat; estudi inicial de llindars. |
| `02-low-detector-thresholds.json` | 3 vídeos, 4 confiances baixes, sense trackers | Executat. |
| `03-localization-candidates.json` | 3 vídeos, 0,001/0,002 | Pla auxiliar conservat. |
| `04-expanded-localization.json` | 18 vídeos, 0,001/0,002 | Executat; revisió humana en curs. |
| `archive/01-detector-confidence.json` | Proposta inicial 0,02/0,05 | Esborrany substituït pel pla robust. |

Les matrius de detectors/trackers són a `config/experiments/`; els plans fixen
quins casos i variants s’executen i quants treballs s’esperen.

## Següent fase: identitat estable

La prioritat passa a associar les deteccions al llarg del vídeo i mantenir
una identitat coherent del gimnasta. L’estudi haurà de distingir:

- Caixa principal suficient i candidates parcials/solapades del mateix actor.
- Identitats d’assistents i altres persones presents.
- Observació real, pèrdua i predicció temporal del tracker.

La tria i la implementació d’aquesta fase queden pendents. La reorganització
actual ordena les eines existents; no executa una nova bateria ni introdueix
un tracker o un recovery nou.
