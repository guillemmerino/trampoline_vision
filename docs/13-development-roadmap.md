# 13. Full de ruta

## Increment 0 — Base documental i estructura

Estat: completat en la creació inicial. Paquet importable sense dependències d'execució, dominis buits amb
responsabilitats descrites, documentació, exemples JSON i carpetes per a proves i experiments.
No inclou algoritmes, servidor, inferència ni puntuació. El fitxer de projecte prepara la futura
instal·lació i no obliga a instal·lar biblioteques visuals per llegir la documentació.

## Increment 1 — Contractes i reproducció d'un cas

Estat: contractes d’entrada, manifest, lector JSON/ZIP/carpeta, ffprobe, CLI i Docker CPU
implementats. La visualització i la comprovació visual de l’alineació són el següent pas.
El lector CSV de compatibilitat continua pendent.

Implementar context de vídeo, esquema BODY_25, deteccions, manifest i font OpenPose JSON/ZIP.
Afegir el lector CSV de compatibilitat quan el primer recorregut estigui comprovat.
Produir una exportació o visualització que permeti comprovar punts i alineació.

Finalització: es carrega el cas de referència, es preserven 930 fotogrames esperats, es distingeix
metadada i pose, es registra la discrepància de durada i es revisa l'alineació sobre el vídeo.
Les proves cobreixen fotogrames buits, ordre dels fitxers, últim fotograma i índex extern.

## Increment 2 — Preparació i seguiment

Implementar validació, deduplicació configurable i un primer tracker amb vida explícita.
Comparar casos amb pose deficient, múltiples actors i desaparicions. Registrar assignacions
i generar vídeo anotat amb trajectòries.

Finalització: una identitat sobreviu als casos breus definits de pèrdua i cap detecció té dues
assignacions. Els casos que continuïn fallant queden identificats, no amagats amb farciments.
El tracker concret i els seus llindars es trien amb evidència dels casos.

## Increment 3 — Subjecte i salts

Construir polítiques de candidats, primera selecció provisional i segmentador interpretable.
Anotar un conjunt petit de salts i trajectòries, sense necessitar puntuacions. Definir la política
de límits i retorn de segments parcials.

Finalització: el recorregut local retorna subjecte o ambigüitat, intervals de salts, informe de
qualitat i vídeo anotat. Hi ha una primera mesura de falsos salts, pèrdues i error temporal.

## Increment 4 — API asíncrona

Exposar el mateix cas d'ús, amb persistència de treballs, inputs i resultats. Formalitzar l'esquema
públic, gestió d'errors, accés i publicació d'artefactes. Afegir l'execució en procés de treball.

Finalització: enviar un cas, consultar-ne l'estat i obtenir els mateixos resultats que amb CLI,
amb errors i intents traçables. El servei no declara readiness si falten capacitats requerides.

## Increment 5 — Inferència integrada amb GPU

Afegir el primer adaptador visual real, pesos explícits, preprocessament i multirotació amb
transformacions verificades. Desar deteccions per poder reproduir resultats sense tornar a inferir.

Finalització: un vídeo nou alimenta els mateixos dominis posteriors; es mesuren cost, cobertura
i duplicats. Aquest increment pot avançar en paral·lel tècnic amb el 4 si hi ha servidor disponible.

## Increment 6 — Avaluadors esportius

Definir indicadors, unitats i escales, anotar correspondències entre salts i valoracions i construir
el benchmark esportiu. Incorporar avaluadors independents i versionats. La precisió i l'abast
de cada resultat s'han de demostrar abans de presentar-lo com una puntuació validada.

No es fixa una estimació de calendari sense haver mesurat les primeres dades i recursos.
