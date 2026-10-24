# 08. Segmentació dels salts

## Objectiu i dependències

El segmentador transforma una trajectòria identificada en intervals de salt i evidència temporal.
No assigna notes i no necessita conèixer els S1…S10 de les metadades. Consumeix mostres amb temps,
punts vàlids i procedència; el filtratge de qualitat precedeix qualsevol ús de geometria derivada.

La primera definició operacional de salt encara s'ha de validar. El producte ha de diferenciar
una seqüència de bots, un element i les possibles fases de contacte i vol, sense donar per resolta
aquesta taxonomia amb la simple detecció d'un màxim o mínim.

## Estratègia inicial proposada

Començar amb senyals temporals interpretables sobre candidats a gimnasta: centre corporal robust,
referències de tronc o pelvis i relació amb la zona de l'aparell quan es conegui. La posició de
la caixa i la mitjana de totes les articulacions són indicadors a contrastar, perquè canvien amb
la postura i els punts absents. No s'anomenen centre de massa físic sense una justificació.

El procés proposat és: construir senyals amb màscares, separar discontinuïtats, aplicar un
filtratge documentat, generar límits candidats, validar-los amb durada i continuïtat i retornar
els segments amb evidència. Les finestres i durades es configuren en segons i es converteixen
segons la línia temporal real.

## Convenció de segment

Cada `JumpSegment` apunta a una persona/trajectòria, un interval `[start_s, end_s)`, fotogrames
de referència, algoritme i versió, qualitat i possibles fases. L'inici i final poden tenir un
estat incert. Els salts tallats per l'inici/final del vídeo es marquen com a parcials i no s'han
d'inventar límits complets.

La política de límits —per exemple contacte a contacte o una altra definició— ha de tenir nom i
versió. Les sortides generades amb polítiques diferents no es comparen com si fossin equivalents.
Els segments d'una mateixa persona segueixen una política explícita sobre solapaments.

## Buits i qualitat

Un buit breu pot admetre interpolació amb un màxim declarat; un buit llarg pot interrompre el
segment o marcar-lo com a no resolt. La cobertura observada i l'estimada s'informen separadament.
La presència d'una trajectòria predita no demostra que hi hagi un salt observable.

Els canvis d'identitat, els punts incompatibles o un tall de pla es tracten com a discontinuïtats.
Una estimació errònia no ha de generar una col·lecció de salts aparentment fiables. Les decisions
de filtratge es conserven perquè es puguin revisar sobre el vídeo.

## Validació inicial

Les primeres anotacions manuals poden limitar-se a intervals i correspondència de persona,
sense notes esportives. Permeten mesurar salts perduts, falsos salts, duplicats i error de límits.
La tolerància temporal s'haurà de fixar abans de comparar algoritmes. Els casos sense salts i
les seqüències parcials són tan necessaris com una rutina completa.
