# 0006. Sessió temporal, confirmació pública i revisió dispersa

- Data: 24/10/2026.
- Estat: accepted per al recorregut de tracking enregistrat.

## Context

El backend escollit retorna deteccions amb ID -1 fins que es confirmen i
exposa estimacions vives mitjançant una propietat pública. El projecte necessita
traçabilitat i estats sense dependre dels atributs interns de la biblioteca.
Els criteris encara no estan calibrats sobre trampolí real.

## Decisió

Mantenir un registre propi de les identitats confirmades, la seva darrera
observació i les transicions lost/recovered/finished. Els IDs -1 queden sense
assignar; no s'inventen IDs provisionals a partir de l'ordre de deteccions.
El vocabulari tentative del contracte continua disponible per futurs backends.

Cada sessió processa fotogrames consecutius des de zero amb timestamps reals.
Un interval visual només limita l'exportació, després d'escalfar el tracker.
El final del tram censura identitats encara vives, sense forçar-ne la desaparició.
Una sessió amb un error després de mutar el backend no es reutilitza.

Publicar un JSONL traçable i un informe de configuració/versions/incidències,
amb vídeo opcional i verificació temporal compartida amb la visualització.
Afegir revisió per anotacions disperses sobre deteccions originals per comparar
configuracions sense exigir encara un corpus dens ni puntuacions esportives.

## Conseqüències i límits

- Les poses i caixes observades no es substitueixen silenciosament per estimacions.
- La primera identitat confirmada no reconstrueix els fotogrames anteriors a posteriori.
- `max_lost_s` es quantitza a les unitats de 30 FPS de la dependència i es registra.
- Les anotacions disperses revelen canvis observats d'ID i unions incorrectes,
  però no produeixen HOTA, IDF1, MOTA ni precisió sobre frames no revisats.
- El cas real encara ha de validar-se; la integració tècnica no implica acceptació esportiva.
- No s'accedeix a estat privat del tracker ni s'ha incorporat un predictor entrenat.

Procediment, sortides i limitacions a la [guia 21](../21-tracking-validation-guide.md).
