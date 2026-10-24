# 02. Abast i requisits

## Escenari de partida

Disciplina: gimnàstica de trampolí. Captura inicial: càmera fixa, vídeo continu i exercici visible.
Hi pot haver diverses persones; la hipòtesi de producte inicial és un gimnasta objectiu per anàlisi.
Si hi ha diversos candidats plausibles, el resultat ha de conservar l'ambigüitat. El sincronitzat,
els canvis de pla i les càmeres lliures requereixen un abast específic posterior.

## Requisits funcionals inicials

| ID | Requisit | Evidència d'acceptació |
| --- | --- | --- |
| IN-01 | Associar vídeo i deteccions precalculades amb un manifest. | Cas carregat amb metadades i origen explícits. |
| IN-02 | Preservar tots els fotogrames de la línia temporal. | Els fotogrames sense deteccions també arriben al seguiment. |
| DATA-01 | Separar metadades, coordenades i confiances. | Importació de `frame,det,kp_*` sense desplaçament de columnes. |
| DATA-02 | Registrar transformacions i esquemes de punts. | Conversió comprovada al fotograma original. |
| TRACK-01 | Mantenir identitats entre observacions. | Trajectòries revisables i assignacions unívoques. |
| TRACK-02 | Gestionar desaparicions i recuperacions. | Temps real transcorregut, estats i motius registrats. |
| SUBJECT-01 | Retornar candidats a gimnasta i política utilitzada. | Selecció explícita o estat ambigu, sense canvis silenciosos. |
| SEG-01 | Retornar intervals temporals dels salts. | Cada segment està vinculat a una trajectòria i a evidència. |
| OUT-01 | Exportar dades i vídeo anotat. | Correspondència verificable entre punts, fotogrames i segments. |
| QUALITY-01 | Informar de cobertura, buits i estimacions. | Informe que permet distingir fallades d'identitat i de pose. |

## Requisits transversals

El nucli s'ha de poder executar sense servidor ni GPU quan les deteccions ja existeixin.
Els imports no carreguen models, no creen directoris, no obren xarxa i no engeguen treballs.
La configuració resolta i la versió del programa s'associen a cada execució. Les dades originals
no es sobreescriuen. Els errors d'entrada, la manca d'un backend i els errors de processament
s'han de diferenciar.

La durada màxima dels vídeos, els límits de memòria, el temps de resposta i el nombre de treballs
simultanis són oberts. Abans de desplegar es mesuraran amb el servidor disponible. Cap número de
rendiment d'un altre dataset s'utilitza com a garantia d'aquest escenari.

## Fora del primer lliurable

No inclou entrenament propi, puntuació esportiva validada, reconstrucció 3D, anàlisi en directe,
interfície web de revisió, seguiment entre càmeres ni sincronitzat. La inferència directa GPU i
l'API són increments planificats, no necessaris per construir el primer lector i tracker.

## Finalització de la primera etapa funcional

Un cas de referència entra per una interfície local, es carrega amb la seva línia temporal,
es converteix al format intern, produeix trajectòries, candidates a subjecte i salts, i genera
un informe i un vídeo que permeten revisar els resultats. Els errors identificats durant la
revisió es converteixen en casos de regressió petits. La primera etapa no implica superar un
llindar de precisió esportiva que encara no s'ha definit ni anotat.
