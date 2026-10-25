# Perfils de recovery en disseny

Tots els exemples són `0.1-draft`, `design-only` i `enabled: false`.
No són configuració executable: canviar enabled a true no activa cap mòdul.
Els loaders i pipelines actuals no els llegeixen.

| Exemple | Intenció futura |
| --- | --- |
| `disabled.example.json` | Conservar el seguiment sense reconstrucció. |
| `geometry.example.json` | Comparar fragments amb temps i moviment. |
| `geometry-appearance.example.json` | Afegir descriptors verificats a la comparació. |

`execution: offline_global` recull el recorregut acordat de tracking complet
seguit de reconstrucció. `mode: audit` reserva la generació de propostes;
el futur apply publicarà també assignacions d'actor. Els camps són un
esborrany i parameters és buit deliberadament: pesos i llindars s'estudiaran.

La referència de model de l'últim perfil no carrega pesos ni descriptors.
Vegeu la [guia del paquet](../../docs/28-recovery-package-design.md).
