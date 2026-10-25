# Configuració de recovery

## Preparació executable (0.6.0)

fragments.json i fragments-disabled.json són esquema 1.0 de la comanda
inspect-fragments. Activar-los prepara observacions consecutives i buits;
desactivar-los valida la font però no crea fragments. No apliquen unions.

## Associació futura

disabled.example.json, geometry.example.json i geometry-appearance.example.json
continuen 0.1-draft, design-only i enabled: false. No són executables i el
lector els rebutja; canviar el booleà no activa rematching. Els criteris i
llindars s'obtindran amb els experiments dels futurs passos 4–6.

El pipeline track continua sense recovery_config. El diagnòstic és posterior
i independent: [guia 29](../../docs/29-recovery-fragment-inspection.md).
