"""Espai reservat per validar enllaços i trajectòries d'actor reconstruïdes.

Comprovarà referències, ordre temporal, absència de cicles, exclusivitat i
coherència de cadena. Una observació no podrà pertànyer a diversos actors.
Les prediccions superposades no equivalen a dues observacions simultànies.

No assumirà que una bona parella garanteix una cadena correcta ni convertirà
ambigüitat en unió forçada. Les invariants de dades i les hipòtesis físiques
experimentals quedaran diferenciades; encara no hi ha validador executable.
"""
