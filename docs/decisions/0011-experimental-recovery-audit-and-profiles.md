# ADR 0011 — Recovery auditable i perfils experimentals explícits

Data: 2026-10-25. Estat:accepted; mode auditoria implementat a 0.7.0.

## Context

El pilot global reconnecta alguns IDs del gimnasta però persisteixen duplicats,
fragments contaminants i sensibilitat als costos. Menys cadenes o canvis d'ID
no garanteixen precisió. Els experiments s'han de poder repetir sense inferència.

## Decisió

- Integrar `audit-recovery` com a cas d'ús posterior i independent de tracking.
- Preservar observacions, prediccions, IDs, procedència i buits originals.
- Publicar enllaços proposats i hipòtesis provisionals, mai apply.
- Exigir perfils executables amb estat experimental, ID/revisió i mode explícit.
- Conservar els drafts anteriors com a disseny rebutjat en execució.
- Desar snapshot/hash del perfil, configuració efectiva, hashes de dades,
  fingerprint del cache i identitat dels bytes de codi en cada run.
- Reutilitzar cache natiu verificat només en lectura, sense fallback a inferència.
- Registrar els pilots a benchmark 07 i les receptes del detector com a receptes,
  diferenciades dels perfils executables. No canviar defaults sobre aquesta prova.

## Conseqüències i límits

Es pot estudiar geometria/aparença/hongarès amb controls reproduïbles. Les
validacions actuals són temporals i de partició; no certifiquen identitat.
Duplicats i discontinuïtats només es marquen. La seva resolució, la coherència
física completa, les anotacions independents i l'activació d'apply continuen obertes.

Alternatives descartades per ara: substituir directament el tracking original,
activar automàticament els perfils experimentals o presentar el pilot d'un sol
vídeo com a recovery fiable.
