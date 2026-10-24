# 12. Estratègia de validació

## Dues validacions diferents

La validació tècnica comprova ingestió, geometria, identitat i segmentació. La validació esportiva
comprovarà la relació entre resultats i puntuacions expertes. El segon benchmark pot arribar
més endavant sense impedir proves útils del primer. Una mètrica LSTM sobre coordenades no és
evidència de bon tracking ni de puntuació correcta.

## Invariants prioritàries

- Tots els fotogrames esperats arriben als consumidors, inclosos els buits i l'últim.
- Una columna `det` mai no es tracta com a coordenada o confiança.
- Les transformacions geomètriques tenen una inversa contrastada en imatges no quadrades.
- La numeració externa es converteix de manera explícita a la interna.
- Detecció i trajectòria tenen identificadors i àmbits diferents.
- L'associació és unívoca i permet no associar quan falta evidència.
- El temps perdut avança una vegada per interval i no assumeix 30 FPS.
- Una observació exacta amb cost zero és vàlida.
- Una predicció no es compta com a observació ni elimina l'avís d'un buit.
- Un segment manté la seva identitat i els seus límits no superen la línia temporal.

## Tipus de proves previstes

`unit/`: transformacions, esquemes, intervals, costos i transicions amb dades petites.
`integration/`: manifest → lector → contracte i, progressivament, recorreguts entre dominis.
`regression/`: casos que reprodueixen errors observats, reduïts al mínim necessari.
`fixtures/`: inputs petits sintètics o extractes revisats; no un dataset complet de vídeos.

No es creen proves que només comprovin que una carpeta existeix o que repliquin literalment el
codi. Ja hi ha proves sobre contractes d’entrada, manifests, JSON, índexs, fotogrames buits, últim
fotograma, timestamps variables i CLI. A Docker també es genera un vídeo sintètic amb FFmpeg
per comprovar ffprobe. Els dominis posteriors afegiran les seves proves quan s’implementin.

## Revisió visual

El vídeo anotat mostrarà punts observats i estimats diferenciats, ID de trajectòria, temps i
límits de segment. Cal revisar mostres a l'inici, final, inversions, agrupacions, pèrdues i
creuaments amb altres actors. La inspecció visual localitza errors; les anotacions permeten
mesurar-los i comparar revisions.

## Mètriques a introduir progressivament

Tracking: canvis d'identitat, fragmentació, cobertura observada, durada dels buits i recuperació.
Pose: error sobre punts anotats i cobertura per articulació, separant posicions difícils.
Segmentació: salts perduts, falsos, duplicats i error de límits amb tolerància temporal definida.
Operació: temps per etapa, memòria i cost addicional de multirotació.

Mètriques estàndard d'associació, com IDF1/HOTA, només es calcularan amb les anotacions i el
protocol necessaris. No es poden derivar de deteccions sense identitat de referència. Els llindars
d'acceptació numèrics continuen oberts i s'establiran abans de la comparativa formal.

## Disseny del conjunt de referència

Incloure clips sense salts, parcials, amb diferents escales del gimnasta, oclusions i altres
persones properes. Les dades de desenvolupament i prova han de separar esportistes/sessions
quan sigui possible. Es registren configuració, versions, procedència i anotacions de cada cas.
Es compararan hipòtesis amb el mateix conjunt, sense retocar el conjunt de prova per afavorir-les.
