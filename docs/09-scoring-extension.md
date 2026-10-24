# 09. Extensió futura de puntuació

## Intenció

La puntuació és l'objectiu final del producte, però la primera etapa construeix l'evidència visual
i temporal necessària. No hi ha cap avaluador implementat en aquest esquelet. El sistema no retorna
una nota fictícia per completar una resposta ni interpreta una confiança visual com a nota.

El vídeo 2D continua sent l'entrada prevista. Els avaluadors definiran quins aspectes poden
observar, amb quines condicions de captura, i quan no disposen de prou evidència. La disponibilitat
d'una estimació 3D pot estudiar-se més endavant, però no és requisit d'aquesta arquitectura.

## Unitat d'avaluació

Un avaluador pot operar sobre un salt, una fase o una rutina. Declara el nivell al qual treballa,
les articulacions i senyals requerits, la versió del criteri, les unitats/escala i les condicions
de qualitat. Consumeix segments i identitats, no formats natius d'un model visual.

Poden coexistir indicadors geomètrics, classificadors d'elements i models de valoració. Una mesura
geomètrica no s'anomena puntuació validada fins que existeixi una correspondència definida i
contrastada amb el criteri esportiu. Les agregacions de rutina són explícites i versionades.

## Resultat proposat

`EvaluationResult` inclouria `evaluator_id`, versió, `segment_id` o referència de rutina, estat,
valor opcional, unitat o escala, qualitat, evidències i motiu quan no es pugui calcular.
Els estats proposats són `computed`, `insufficient_data`, `unsupported` i `not_implemented`.
Un avaluador obligatori absent genera un error de configuració abans d'executar; un resultat
`not_implemented` només s'utilitza per una capacitat futura declarada com a opcional.

Un valor absent és null. Un valor zero és una dada vàlida i no representa absència. Si s'arriba
a publicar incertesa estadística d'una nota, es documentarà el seu significat i com s'ha calibrat.
La qualitat visual per si sola no és un interval de confiança de la puntuació esportiva.

## Anotacions i entrenament futurs

Les notes de les metadades anteriors es mantenen separades dels inputs visuals. L'assignació
nota-salt requereix correspondències revisades; no es dedueix automàticament per posició dins
la seqüència. També s'hauran de documentar escales, anotadors i possibles desacords.

Els futurs conjunts d'entrenament i prova s'han de separar per esportista, rutina o sessió segons
el cas, evitant compartir fragments del mateix exercici entre grups. Els models i les escales
de puntuació no s'escullen en aquesta fase. Un benchmark esportiu formal arribarà després de la
validació tècnica del tracking i la segmentació.
