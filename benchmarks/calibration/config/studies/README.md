# Plans en curs

El [protocol de continuïtat d’identitat v1](identity-continuity-v1.md) i el seu
[pla executable](identity-continuity-v1.json) comparen quatre perfils sobre
tres vídeos complets amb deteccions enregistrades. El wrapper fa preflight
per defecte. La bateria ja està executada i té una
[revisió provisional](../../reviews/identity-continuity-v1/README.md), amb
anotació temporal encara incompleta i cap guanyador validat.
Consulta [l’estat actual](../../docs/STATE.md).

El [prototip de tracking per al trampolí](trampoline-tracker-prototype-v1.md)
compara predictors, admissió feble i desempat amb aparença sobre simulacions
i les candidates congelades dels tres vídeos.

La [simulació de confiança i silueta](trampoline-silhouette-v1.md) compara
el tall fix, la confiança YOLO com a cost suau i el suport de primer pla.

El [catàleg de casos per a recovery](recovery-case-catalog-v1.md) fixa
18 finestres del tracker amb velocitat simple per revisar buits,
transferències i continuïtat abans d’avaluar l’auditoria actual.

La [primera prova de recovery geomètric](recovery-geometry-v1.md) compara
l’auditoria existent amb la traça congelada i les àncores del catàleg.

La [simulació del camí del gimnasta](recovery-subject-path-simulation-v1.md)
contrasta el camí complet, la decisió local i l’ambigüitat en escenes sintètiques.

La [prova del camí geomètric del gimnasta](recovery-subject-path-v1.md)
contrasta el graf amb el tracker i l’hongarès als tres vídeos complets.

Els plans nous han d’explicitar vídeos, variants, referències, política de
cache, abast, sortides i criteris de revisió. En tancar l’estudi, mou el pla
i les evidències seleccionades a `archive/<estudi>/` i actualitza els índexs.
No deixis aquí plans tancats amb aparença de configuració activa.
