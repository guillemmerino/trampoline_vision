# Documentació de Trampoline Vision

Data de la base documental: 24 d'octubre de 2026. Aquesta documentació descriu el disseny acordat
i el pla d'implementació; no implica que les funcionalitats ja estiguin disponibles.

## Ordre de lectura

| Document | Contingut |
| --- | --- |
| [01. Intenció](01-project-intent.md) | Producte, objectiu 2D i principis. |
| [02. Abast i requisits](02-scope-and-requirements.md) | Primer lliurable, límits i acceptació. |
| [03. Arquitectura](03-architecture-and-domains.md) | Dominis, dependències i recorreguts de dades. |
| [04. Contractes](04-data-contracts.md) | Semàntica dels objectes interns. |
| [05. Entrades](05-inputs-and-legacy-data.md) | Cas existent, formats OpenPose i sincronització. |
| [06. Percepció](06-perception-and-multirotation.md) | Adaptadors, models i multirotació. |
| [07. Tracking](07-tracking-and-subject-selection.md) | Identitat, recuperació i selecció del gimnasta. |
| [08. Segmentació](08-jump-segmentation.md) | Salts, fases i ambigüitats. |
| [09. Puntuació](09-scoring-extension.md) | Extensió esportiva futura i anotacions. |
| [10. Configuració](10-configuration.md) | Models, escenaris, pipelines i precedència. |
| [11. API i execució](11-api-and-execution.md) | Treballs asíncrons i desplegament futur. |
| [12. Validació](12-validation-strategy.md) | Invariants, regressions i benchmark. |
| [13. Full de ruta](13-development-roadmap.md) | Increments i criteris de finalització. |
| [14. Desenvolupament](14-development-guide.md) | Convencions i ordre de construcció. |
| [15. Execució CPU](15-cpu-replay-guide.md) | Comandes, formats implementats i resultats de lectura. |
| [16. Lectura del codi](16-code-reading-guide.md) | Ordre de lectura, contractes, funcions i configuracions. |
| [17. Visualització](17-visualization-guide.md) | Vídeo anotat, filtres visuals i verificació temporal. |
| [18. Revisió del cas](18-reference-visual-review.md) | Artefactes generats, comprovacions i observacions del vídeo actual. |
| [19. Contractes de tracking](19-tracking-contracts-and-backend.md) | Backend OC-SORT escollit, contractes implementats, proves i límits. |
| [Decisions](decisions/README.md) | Registre de decisions arquitectòniques. |

## Estat de les decisions

- **Adoptada:** forma part del disseny de partida i ha de guiar la implementació.
- **Proposada:** hipòtesi concreta que requereix proves o una decisió posterior.
- **Oberta:** encara no hi ha una elecció; no s'ha de convertir en un requisit implícit.
- **Implementada:** només s'utilitzarà quan existeixin el codi i la verificació corresponents.

Estan implementats Docker CPU, els contractes bàsics d’observacions, el lector JSON/ZIP o carpeta,
el manifest 1.0, la línia temporal ffprobe i les CLI d’inspecció i visualització amb proves. El tracking, la
segmentació i l’API continuen pendents. Els contractes de tracking per fotograma ja estan
implementats i el backend inicial està escollit; l'adaptador encara no s'executa.
Els altres contractes avançats i les rutes API són propostes.
Els canvis de comportament hauran d'actualitzar el document afectat i, si canvien una frontera
o una decisió important, afegir un registre a `decisions/`.

## Lectura segons la tasca

Per construir el primer lector: 04, 05, 10 i 12. Per treballar el tracking: 03, 04, 06 i 07.
Per detectar salts: 04, 07, 08 i 12. Per integrar la plataforma: 04, 10 i 11.
El document 09 defineix l'extensió de puntuació, però no bloqueja el primer recorregut funcional.
