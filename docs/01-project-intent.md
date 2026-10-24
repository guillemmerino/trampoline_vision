# 01. Intenció del projecte

## Objectiu del producte

Trampoline Vision vol analitzar un exercici de gimnàstica de trampolí a partir d'un vídeo 2D i
retornar un diagnòstic esportiu: moviments identificats, indicadors observables i, progressivament,
puntuacions. El vídeo 2D és l'entrada principal prevista. La reconstrucció 3D no és un requisit
de partida ni una condició per començar a obtenir informació útil.

La perspectiva fixa semblant a una vista de jutges és una hipòtesi de captura adequada al producte.
La relació entre els indicadors visuals i les valoracions esportives s'haurà de validar amb dades
de referència. No s'assumeix que qualsevol càmera o qualsevol indicador geomètric permetin obtenir
automàticament una nota esportiva correcta.

## Primer problema que resolem

Els vídeos poden incloure diversos actors: gimnastes, entrenadors, jutges i públic. El sistema
ha de conservar la identitat de les persones rellevants i identificar els salts del gimnasta,
també quan canvia molt de postura, queda cap per avall o es detecten només algunes articulacions.

La primera etapa produeix trajectòries, candidats a gimnasta, segments de salt i evidència visual.
La nota d'execució i altres puntuacions arribaran quan s'hagin definit i validat els avaluadors.
No hi haurà resultats aleatoris que aparentin ser una valoració funcional.

## Relació amb TFM

El projecte anterior és una font d'experiments, dades i casos de fallada. Es poden adaptar idees
útils després de revisar-ne les hipòtesis, però el paquet nou no importa els seus scripts ni
hereta les seves dependències globals. Les dades existents es consumeixen amb adaptadors d'entrada.
Les correccions necessàries es fan en la interpretació del nou sistema, preservant els originals.

## Principis adoptats

1. Identitat, pose, segmentació i puntuació tenen responsabilitats diferents.
2. La sortida d'un model extern es transforma a contractes interns abans de passar als dominis.
3. La multirotació és una via inicial prevista perquè no hi ha un banc propi per entrenar models.
4. LSTM i altres predictors temporals són opcionals i han de demostrar utilitat abans d'incorporar-se.
5. Cada resultat conserva vídeo, temps, persona, configuració i procedència dels seus inputs.
6. Les observacions i les estimacions es distingeixen durant tot el recorregut.
7. La qualitat informa sobre buits i ambigüitats; no es converteix automàticament en una nota esportiva.
8. El desenvolupament local sense GPU pot avançar reproduint deteccions enregistrades.

## Decisió de producte pendent

Continuen oberts el criteri definitiu de selecció del gimnasta, els algoritmes de tracking i
segmentació, els models visuals, les escales de puntuació i els objectius de rendiment.
El servidor final disposarà de GPU; la memòria disponible i la concurrència encara s'han de concretar.
La primera implementació ha d'ajudar a prendre aquestes decisions amb casos revisables.
