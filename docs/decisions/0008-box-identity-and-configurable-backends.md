# 0008 — Identitat temporal de caixes i backends substituïbles

Estat: implementada a 0.5.0. Data: 25 d'octubre de 2026.

El detector independent del projecte anterior cobreix millor el moviment
que les caixes derivades d'articulacions incompletes. El pilot 05 indica que
l'aparença pot ajudar, però no resol tots els canvis d'actor ni la fragmentació.
Cal incorporar aquestes opcions sense acoblar el domini a un model concret.

El tracker de caixes és propietari de la identitat temporal. Un matching
posterior associarà poses independents amb aquestes identitats. No s'utilitza
`det_id`, ordre d'OpenPose ni un esquelet fictici com a identitat.

S'adopten un port de backend, una factoria explícita i perfils versionats
per OC-SORT, ByteTrack i BoT-SORT, amb/sense ReID extern. La sessió conserva
la política de naixements i les transicions comunes. Perception produeix
descriptors normalitzats; infraestructura els persisteix sense decidir tracks.
Els adaptadors fixen les APIs de biblioteca i declaren els límits reals.

Es manté el recorregut OpenPose anterior per regressió i comparació. Les
noves proves no entrenen models ni impliquen que el benchmark sigui una
avaluació formal de precisió. Coherència, matching, selecció del gimnasta,
salts, API i puntuació continuen sent increments diferenciats.

Aquesta decisió amplia la 0005, que limitava la primera implementació a
OC-SORT; manté la separació de fronteres i la política de la 0007.
