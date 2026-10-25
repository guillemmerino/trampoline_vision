# 31. Banc de calibratge portable per al servidor

25/10/2026. Estat: executor experimental implementat, dades copiades i
verificació CPU. No és una validació de precisió ni un canvi de defaults.

L'objectiu és poder actualitzar el codi amb Git, traslladar un paquet de
vídeos/pesos identificat i executar una bateria amb una comanda al servidor
Linux/NVIDIA. L'API no és una dependència d'aquest experiment.

El [protocol i les comandes](../benchmarks/calibration/README.md) descriuen
preparació, transferència, construcció GPU, smoke/pilot/all, represa,
recursos, artefactes i referències manuals. `corpus.json` fixa els 94 vídeos;
la suite pilot en selecciona 18, sis per grup de font, amb 9 min 36 s.

El detector experimental exporta el CSV canònic i el banc crida el mateix
`application.tracking.track_case` que la CLI. No incorpora scripts de TFM
com a dependència, no canvia la propietat de la identitat i no barreja poses
amb caixes. El matching OpenPose, la selecció de subjecte, els salts i la
puntuació continuen fora d'aquest recorregut. Recovery continua en el seu
mode audit independent, sense apply.

Es comparen model/confiança/NMS/top20 del detector, amb les mateixes deteccions
per als quatre perfils existents. Un segon experiment estudia confiança forta
i retenció del tracker amb detector fix. Es registren configuració efectiva,
hashes, versions reals, temps, recursos i ús de cache. No hi ha cerca automàtica
ni funció de qualitat agregada sense criteris d'acceptació acordats.

Les referències opcionals són caixes del vídeo original amb hash de vídeo,
independents dels IDs del detector. Sense revisió explícita no es calcula
qualitat del gimnasta. Els comptadors de fragments i IDs de tots els actors
són diagnòstics, no criteris suficients per consolidar una configuració.

Cal completar anotacions independents, definir acceptació i contrastar els
finalistes amb fonts reservades abans d'escollir defaults. Els 94 clips són
un corpus exploratori del mateix entorn; no constitueixen un holdout independent.
La GPU concreta del servidor encara requereix preflight i validació reals.

La [mostra d'anotació provisional](../benchmarks/calibration/annotation-pilot/README.md)
prepara 72 frames de tres vídeos: 61 caixes visuals del model i 11 exclusions.
Conserva originals, hashes, correccions d'overlay i galeria. Les referències
provisional requereixen `--allow-provisional-references` i no es publiquen
com a revisió humana. La comparació de traces històriques serveix per comprovar
el procediment; no selecciona defaults ni substitueix les anotacions independents.
