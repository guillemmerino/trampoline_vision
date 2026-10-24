# 11. API i execució

## Cas d'ús compartit

L'aplicació definirà una operació d'anàlisi sobre un vídeo, una font de deteccions o configuració
d'inferència, un escenari i opcions de sortida. CLI, procés de treball i API cridaran aquesta
operació. Els algoritmes no coneixeran objectes HTTP ni rutes de contenidors.

El primer recorregut s'executarà localment amb deteccions enregistrades. Després s'exposarà per
API i s'incorporarà inferència GPU. Les CLI `inspect`, `visualize` i `track` ja executen
ingestió, revisió visual i seguiment enregistrat; `evaluate-tracking` revisa anotacions.
L'API i els endpoints continuen pendents.

## API asíncrona proposada

| Operació | Ruta provisional | Resposta prevista |
| --- | --- | --- |
| Enviar vídeo i opcions | `POST /v1/analyses` | HTTP 202, ID de treball i URL d'estat. |
| Consultar estat | `GET /v1/analyses/{id}` | Estat i etapa actual; error estructurat si n'hi ha. |
| Recuperar resultat | `GET /v1/analyses/{id}/result` | Resultat versionat quan estigui disponible. |
| Consultar artefactes | `GET /v1/analyses/{id}/artifacts` | Referències autoritzades a vídeo anotat i dades. |

El transport inicial es proposa com a càrrega de fitxer. L'ús d'un object store compartit és una
decisió posterior. No s'acceptaran rutes arbitràries del servidor com a contracte públic.
Els camps concrets i els codis d'error es formalitzaran abans d'implementar el servei.

## Vida d'un treball

Estats proposats: `queued`, `running`, `succeeded`, `failed` i `cancelled`. Les etapes internes
poden informar de ingestió, preparació, tracking, segmentació i exportació. El progrés no promet
un temps restant exacte. La cancel·lació serà cooperativa entre etapes o lots.

Els intents d'un treball es distingeixen amb un ID d'intent. Només es publica un resultat complet
quan els artefactes obligatoris estan confirmats; un fitxer parcial no marca l'anàlisi com a feta.
La futura política d'idempotència haurà de considerar entrada i configuració. No es reexecuten
errors deterministes d'entrada indefinidament.

## CPU i GPU

En mode enregistrat, els dominis poden córrer en CPU sense instal·lar backends GPU. En inferència,
el procés de treball carrega els pesos explícits i limita la concurrència segons memòria GPU.
El nombre de processos, el batching i la memòria màxima es decidiran amb mesures del servidor.
Un estat mutable de tracking mai no es comparteix entre vídeos simultanis.

## Persistència, accés i salut

La infraestructura gestionarà inputs, resultats, retenció i accés per anàlisi. El mecanisme
d'autenticació s'integrarà amb la plataforma esportiva quan se'n conegui el contracte.
Una comprovació de liveness informa que el procés viu; readiness comprova les capacitats
necessàries i respon amb un estat HTTP de fallada quan no estan disponibles.

Els logs inclouran `run_id`, vídeo, etapa i component, sense dades de vídeo completes ni credencials.
Temps per etapa, buits i fallades de model són mesures operatives diferents de les mètriques
de precisió. Docker, servidor HTTP i motor de cues encara no estan seleccionats ni implementats.
