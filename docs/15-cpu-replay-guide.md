# 15. Guia d'execució CPU: passos 1 i 2

## Què executa

La comanda `inspect` llegeix el vídeo original amb ffprobe, obté marques temporals per fotograma,
obre les deteccions OpenPose i les converteix al contracte intern 1.0. No torna a executar OpenPose,
no deduplica, no assigna identitats, no detecta salts i no genera un vídeo anotat.

El pas 3 afegirà la visualització per comprovar l'alineació. L'índex extern declarat al manifest
permet sincronitzar per numeració, però encara no constitueix una comprovació visual.

## Docker CPU

El Dockerfile té un builder de wheel, un target `cpu` i un target `test`. El runtime inclou
Python 3.11 i FFmpeg/ffprobe, i executa com a usuari sense privilegis. No conté CUDA, pesos,
vídeos ni biblioteques de models. Compose deixa la imatge en mode només lectura, `/tmp` temporal,
TFM muntat només per a lectura i `runs/` com a sortida.

La construcció requereix accés als registres Python/Debian i de contenidors. Les etiquetes de base
i les dependències del sistema no constitueixen encara un lock complet per digest; les versions
es poden consultar dins de la imatge. La fixació completa és una tasca posterior de desplegament.

Des del projecte, a PowerShell:

```powershell
New-Item -ItemType Directory -Force runs | Out-Null
docker compose build replay
docker compose run --rm replay --help
docker compose run --rm replay inspect --config configs/pipelines/inspect-openpose.json --output runs/reference-summary.json
docker compose --profile test build tests
docker compose --profile test run --rm tests
```

A Linux, crear `runs/` amb `mkdir -p runs` i donar permisos a l'usuari 1000 del contenidor.
No cal iniciar un servei persistent: cada `docker compose run --rm` processa una comanda i acaba.
`TFM_DATA_DIR` pot substituir `../TFM`, però la disposició de fitxers del manifest també ha de coincidir.

## Manifest i font

El manifest 1.0 declara el vídeo, la font primària, la base d'índex (0 o 1), BODY_25 i coordenades
del fotograma original. Suporta `openpose_json_zip` i `openpose_json_directory`. Els noms acceptats
inclouen `frame_000001_keypoints.json` i `prefix_frame_000001_keypoints.json`, també en subcarpetes.
No s'infereix l'índex de qualsevol nombre arbitrari dins d'un nom desconegut.

Un registre JSON ha de contenir `people` com a llista i 75 nombres finits per persona a
`pose_keypoints_2d`. La confiança ha d'estar dins de [0,1]. Confiança zero implica punt absent;
una coordenada zero amb confiança positiva es conserva. Els punts fora de la imatge s'etiqueten,
no es retallen ni s'eliminen. Un cost de qualitat o deduplicació encara no s'hi aplica.

Es llegeix cada membre ZIP directament, amb límit de 16 MiB per JSON. No s'extreu al disc.
Índexs duplicats, fora de rang, JSON malformat o esquema incorrecte generen error. Un JSON absent
és diferent de `people: []`: amb política `report`, es genera un fotograma `missing` i un avís;
amb `error`, s'atura la lectura. Una font sense cap JSON és un error.

## Temps del vídeo

ffprobe descodifica informació de fotogrames a CPU, sense executar cap model. Les marques de
presentació es normalitzen respecte de la primera i es conserva l'origen original. La durada
entre fotogrames es calcula amb aquestes marques, també en vídeos de FPS variable.

L'última durada utilitza `duration_time`/`pkt_duration_time` si existeix. Si no, es fa una estimació
de la mediana dels intervals o de FPS per a un únic fotograma, sempre amb avís. No s'accepten
marques absents o no creixents, dimensions variables ni rotació de visualització sense normalitzar.
No s'apliquen transformacions implícites que desalineïn deteccions.

## Sortides

`--output` desa un informe JSON amb versió, ID d'execució, fonts, opcions, dimensions i temps,
comptes de deteccions/punts, absències i avisos. Sense aquesta opció, l'informe va a stdout.
La discrepància 25/31 s del cas de referència es registra com `reference_duration_mismatch`.
Les notes S1…S10 no es llegeixen ni s'utilitzen per analitzar el vídeo.

`--frames-output` és opcional i genera JSONL: una línia per fotograma intern, inclosos els buits.
Cada detecció conté punts amb nom, confiança, validesa i origen. No hi ha cap `track_id`.
S'acumula només el registre actual de deteccions; el vídeo sí que conserva la línia temporal
completa i la font manté un índex dels noms de registres.

La lectura es completa en fitxers temporals abans de publicar les sortides. No se sobreescriuen
fitxers existents. La publicació dels dos artefactes no és una transacció conjunta: l'informe
final és la confirmació del recorregut complet. Una publicació interrompuda no és un treball API
complet; la persistència transaccional correspon a un increment posterior.

## Errors i proves

La CLI retorna 0 si completa la lectura amb o sense avisos i 2 si hi ha un error d'entrada,
sondeig, configuració o sortida. Si no hi ha ffprobe local, indica utilitzar Docker o instal·lar
FFmpeg. Els models, CSV heretats, pipelines de disseny i punts COCO no activen un fallback ocult.

Les proves usen dades sintètiques petites. La prova d'integració crea un MP4 temporal amb FFmpeg
i comprova dimensions, 3 fotogrames, durada i sortida CLI. El cas real es comprova separadament,
amb els seus inputs en només lectura. No s'interpreten aquestes comprovacions com a benchmark
de precisió de tracking o de puntuació.

## Comprovació inicial del cas existent

El 24 d'octubre de 2026 s'ha construït la imatge CPU i han passat les 22 proves dins de Docker,
inclosa la integració amb vídeo sintètic. La lectura del ZIP de referència ha produït 930 fotogrames,
31 s, 89.725 deteccions i cap registre absent. Aquests comptes corresponen al ZIP, no al CSV derivat,
que és un artefacte diferent. S'han informat el desajust de durada i la verificació visual pendent.
No s'han mesurat encara precisió de pose, identitats ni salts.

Referències de les eines: [serveis Compose](https://docs.docker.com/reference/compose-file/services/),
[ffprobe](https://ffmpeg.org/ffprobe.html) i [pyproject.toml](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/).
