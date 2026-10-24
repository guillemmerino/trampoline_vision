# 05. Entrades i dades heretades

## Fonts previstes

El primer adaptador ja consumeix vídeo i deteccions JSON enregistrades. Més endavant, una font d'inferència
consumirà només vídeo i configuració del model. Els dos recorreguts han de produir `FrameDetections`
sobre la mateixa línia temporal, sense que el tracker conegui el format extern.

## Cas inicial comprovat

El cas de desenvolupament és `JPN_AGE_1_000905_31.0` del projecte germà TFM. Les observacions
següents provenen d'una inspecció de fitxers, no d'una anotació de qualitat esportiva:

| Artefacte relatiu a TFM | Informació |
| --- | --- |
| `jumping_score/output_clips/JPN_AGE_1_000905_31.0.mp4` | 960 × 1080, 30 FPS, 930 fotogrames; durada derivada de 31 s. |
| `Tracking_system/output_videos/JPN_AGE_1_000905_31.0_fused_json.zip` | 930 JSON, de `frame_000001_keypoints.json` a `frame_000930_keypoints.json`. |
| `Tracking_system/csv/real_2/JPN_AGE_1_000905_31.0fused_salida.csv` | `frame`, `det` i 75 valors BODY_25 intercalats X/Y/confiança. |
| `jumping_score/output_clips/clips_metadata_AGE_1.csv` | CSV separat per punt i coma; la fila del clip declara 25 s i una meitat de pantalla. |

La durada de metadades no coincideix amb la del vídeo. La línia temporal de l'anàlisi prové del
vídeo; el desajust es registra. La mostra inspeccionada del JSON fusionat té `version` i `people`,
amb `pose_keypoints_2d` per persona. No informa de l'angle de procedència de cada detecció.

## Manifest per cas

El [manifest d'exemple](../data/manifests/JPN_AGE_1_000905_31.0.example.json) associa fonts
explícitament. Les rutes relatives d'un manifest es resolen respecte de la seva carpeta. Es
declaren esquema, espai de coordenades, base d'índex i variant heretada. No s'infereix identitat
a partir de l'ordre de deteccions, l'àrea o el número `det`.

El manifest de referència és executable i utilitza l’esquema 1.0. Les rutes apunten al projecte germà
previst i s'hauran d'ajustar si les dades es mouen. No hi ha còpia de vídeos o deteccions al paquet.
Els valors coneguts són comprovacions inicials, no substitueixen la lectura del vídeo en executar.

## Lector OpenPose JSON/ZIP

Ha de llegir directament els membres JSON del ZIP quan sigui possible, sense necessitar una
extracció completa. Ordena per índex de fotograma, valida longituds múltiples de tres i conserva
els 25 punts. `people: []` és un fotograma vàlid sense deteccions. S'han de detectar membres
duplicats, índexs fora de rang i absències; un error de lectura no es converteix en un fotograma
buit sense avisar. El vídeo determina els fotogrames esperats, inclosos els que no apareguin al ZIP.

En el cas inicial es proposa convertir índex extern N a índex intern N-1. Aquesta regla es
valida visualment sobre mostres, perquè igualtat de recomptes no garanteix alineació exacta.
Les deteccions fusionades ja declarades en coordenades originals no es tornen a desrotar.

## Lector CSV heretat (pendent d’implementació)

Ha de seleccionar les columnes de punts pel nom i l'ordre numèric declarat. `frame`, `det`, àrees
i altres metadades es mantenen fora dels vectors de pose. Es validen els 75 camps BODY_25 i la
separació X/Y/confiança. Es reconstrueix una llista per fotograma; els salts d'índex generen buits
explícits. No es descarta un actor perquè no tingui la caixa més gran.

## Metadades i anotacions

Els camps S1…S10 són referència externa futura i no entren al tracker, al selector ni al segmentador.
Una futura assignació entre notes i salts requerirà anotació explícita, sense assumir que els
últims deu segments coincideixen amb les deu notes. Les rutes `/clips/...` del sistema anterior
es tradueixen mitjançant el manifest; no són rutes del nou servidor.
