# 07. Seguiment i selecció del gimnasta

## Seguiment de múltiples persones

El tracker manté identitats perquè l'escena conté més actors que el gimnasta objectiu. Una identitat
no depèn de conservar tots els punts de la pose. Es poden combinar moviment, caixes, evidència de
pose i aparença quan estigui disponible; cap algoritme concret està adoptat encara.

L'objectiu inicial és una associació coherent i auditable. Afegir diversos predictors sense
mesurar-los no és un criteri de qualitat. Un predictor temporal, inclòs LSTM, només s'incorporarà
si millora casos de referència sense augmentar canvis incorrectes d'identitat.

## Cicle de vida proposat

Una trajectòria pot estar pendent de confirmació, activa, perduda temporalment o finalitzada.
Les transicions tenen marca temporal i motiu. Un fotograma buit avança igualment la predicció i
l'edat de les trajectòries. El temps perdut es compta una vegada per interval i en segons reals.
La política de confirmació, desaparició i recuperació és configurable i encara s'ha de calibrar.

La detecció és una mesura; l'estat predit és una estimació. Si no hi ha observació, es pot mantenir
una hipòtesi limitada en el temps, però no crear articulacions amb confiança d'observació.
La incertesa ha de créixer o reflectir que s'ha perdut evidència.

## Associació

Les assignacions d'un fotograma són unívoques: una detecció no alimenta dues trajectòries i una
trajectòria no absorbeix dues persones. Les parelles incompatibles es rebutgen i es permet deixar
una detecció sense associar. La funció de cost ha d'utilitzar unitats compatibles i distingir
absència d'evidència de cost geomètric real. Un cost zero és vàlid.

La rotació del cos, l'agrupació o la pèrdua de peus poden variar molt la caixa derivada de pose.
Els llindars s'han de provar en aquests casos. Es registraran motius de rebuig, recuperacions,
canvis sospitosos i trajectòries curtes, amb nivell de detall configurable.

## Refinació temporal

La interpolació i el filtratge operen dins d'una identitat, preservant punts originals, interval
interpolat i paràmetres. No s'interpolen silenciosament buits llargs ni es travessen canvis de
persona. Les estimacions es poden usar per estabilitzar l'associació, però els consumidors reben
la seva procedència i poden excloure-les per segmentar o puntuar.

## Selecció del gimnasta

`subjects` és una política separada. Es compararan selecció per zona de l'aparell, persistència,
moviment repetit compatible amb salts i una indicació inicial opcional. No hi ha una política
definitiva. La zona ha d'incloure el volum de vol visible, no només el llit de l'aparell.

La selecció pot ser provisional. L'aplicació pot segmentar diversos candidats i retornar aquesta
evidència al selector. El resultat especifica quina política s'ha utilitzat i si hi ha diversos
candidats plausibles. No es canvia de gimnasta fotograma a fotograma segons confiança mitjana.

## Fragments i múltiples candidats

Si una mateixa persona queda en diversos fragments, la reconciliació és explícita i reversible
en els resultats. No es concatenen fragments només perquè se solapen en el temps amb salts.
Si hi ha dos gimnastes simultanis, es preserven els seus segments i l'estat de selecció. Aquesta
situació no es converteix automàticament en suport de trampolí sincronitzat.
