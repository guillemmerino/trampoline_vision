# ADR 0012 — Considerar totes les caixes seleccionades per mantenir un ID

Data: 2026-11-21  
Estat: `accepted` com a decisió de disseny del tracker propi.

## Context

La preparació ordena les caixes amb evidència de silueta, confiança YOLO
i posició, i en conserva fins a 12 per fotograma. Els perfils actuals de
BoT-SORT i ByteTrack apliquen un segon llindar de confiança quan associen
les caixes. A AGE2, tres candidates útils que havien quedat primeres al
rànquing tenien un score YOLO inferior a 0,02 i BoT-SORT les va excloure.

## Decisió

**Totes les caixes que han passat el tall de preparació són elegibles
per associar-se a un ID ja confirmat, independentment de la confiança
YOLO.** El tracker propi no aplica cap segon tall per confiança en
aquesta associació.

El score original de YOLO es conserva i es pot usar com a penalització
suau en el cost d’associació. La compatibilitat amb el moviment, la
competència entre actors i l’opció de deixar el track sense observació
continuen formant part de la decisió. La confirmació d’un ID nou manté
una política separada d’evidència forta.

## Evidència i conseqüències

Amb el mateix predictor de velocitat, la penalització suau ha mantingut
l’ID en 134 de 202 parells anotats, davant de 127 amb un tall fix de 0,001.
Guanya set parells i conserva tots els que mantenia el control. La prova
és provisional i mesura la continuïtat als extrems anotats. El suport
de silueta en el cost continua sent experimental. [Resultats de la simulació](../../benchmarks/calibration/config/studies/trampoline-silhouette-v1.md)

Els talls fixos a 0,02 i 0,001 es mantenen com a controls experimentals.
L’acceptació d’aquest ADR fixa el comportament del futur tracker propi.
Els perfils actuals de producció conserven la seva configuració.
