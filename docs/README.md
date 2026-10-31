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
| [20. Preparació de candidats](20-pose-candidate-preparation.md) | Caixes, confiança, deduplicació opcional i ús des de Python. |
| [21. Validació del tracking](21-tracking-validation-guide.md) | CLI, identitats, exportació/vídeo, anotacions i iteració de criteris. |
| [22. Primer baseline real](22-first-tracking-baseline-review.md) | Proves 0–3/14–17 s, canvi d'identitat i limitació de reconfirmació descoberta. |
| [23. Correcció i millores](23-confirmation-fix-and-improvement-study.md) | Confirmació 0.4.0, regressió i tres experiments de configuració. |
| [24. Diagnòstic de geometria i evidència feble](24-final-geometry-and-weak-evidence-diagnosis.md) | Set prototips aïllats, ByteTrack, revisió de caixes i decisió del següent increment. |
| [25. Tracking amb caixes independents](25-independent-box-tracking-study.md) | Set proves amb YOLO enregistrat, mostra de trajectòria i límits de continuïtat. |
| [26. Comparació amb ReID](26-reid-tracking-comparison.md) | Tres clips, BoT-SORT amb/sense aparença, vídeos comparatius i cache per refinar. |
| [27. Tracking configurable](27-configurable-box-tracking.md) | Identitat de caixes, quatre perfils, ReID extern, cache i Docker. |
| [28. Estructura de recovery](28-recovery-package-design.md) | Reconstrucció posterior al tracking: fitxers reservats, perfils de disseny i pla de construcció. |
| [29. Diagnòstic de fragments](29-recovery-fragment-inspection.md) | Contractes, lectura completa, fragmentació, CLI i continuació 4–6. |
| [30. Auditoria experimental de recovery](30-experimental-recovery-audit.md) | Propostes globals, perfils explícits, cache verificat i registre d'experiments; sense apply. |
| [31. Calibratge al servidor](31-server-calibration-benchmark.md) | Corpus portable, bateries de detector/tracking, Linux/NVIDIA, represa i referències independents. |
| [32. Avaluació del calibratge](32-tracker-calibration-assessment.md) | Aportació de la prova GPU, límits de les mètriques i pla per calibrar el tracker sense recovery offline. |
| [Decisions](decisions/README.md) | Registre de decisions arquitectòniques. |

## Estat de les decisions

- **Adoptada:** forma part del disseny de partida i ha de guiar la implementació.
- **Proposada:** hipòtesi concreta que requereix proves o una decisió posterior.
- **Oberta:** encara no hi ha una elecció; no s'ha de convertir en un requisit implícit.
- **Implementada:** només s'utilitzarà quan existeixin el codi i la verificació corresponents.

Estan implementats Docker CPU, els contractes bàsics d’observacions, el lector JSON/ZIP o carpeta,
el manifest 1.0, la línia temporal ffprobe i les CLI d’inspecció, visualització i tracking.
El seguiment integra preparació, deduplicació opcional i adaptador OC-SORT amb registre
temporal, JSONL, informe i vídeo opcional. Hi ha diagnòstic d'anotacions disperses i
proves sintètiques; la precisió sobre el vídeo real continua pendent de validació.
La primera revisió real ja s'ha executat: el baseline falla en continuïtat d'identitat
i revela una limitació de reconfirmació de l'adaptador; veure document 22.
La limitació de reconfirmació ja està corregida a 0.4.0 amb 95 proves i
noves execucions reals; els canvis d'actor continuen pendents de resolució, veure document 23.
L'estudi 04 ja prova les caixes YOLO independents sobre el clip complet:
milloren la cobertura, però persisteixen fragmentació i transferències d'actor.
Hi ha una mostra local revisada amb prediccions i ambigüitats explícites;
veure document 25. L'associació de poses independents encara no s'ha validat.
L'estudi 05 compara OC-SORT i BoT-SORT amb/sense ReID en tres clips complets.
L'aparença redueix els canvis mínims entre matches revisats, però encara hi ha
fragmentació. Es conserven vídeos, trajectòries i cache de descriptors per
refinar sense repetir inferència; veure document 26. El backend de producció
es va mantenir sense canvis durant aquest pilot.
A 0.5.0 el seguiment de caixes ja té adaptadors configurables OC-SORT, ByteTrack
i BoT-SORT amb/sense ReID extern, CSV canònic i cache verificat. El matching de
poses i la coherència de l’actor continuen pendents; veure document 27.
A 0.6.0 el primer increment de recovery prepara fragments del tracking complet,
amb contractes, validació, informe/JSONL i visualització. Encara no uneix tracks
ni assigna actors; passos futurs 4–6 al document 29.
A 0.7.0 `audit-recovery` implementa propostes globals i hipòtesis provisionals,
amb perfils experimentals i registre a benchmark 07. No aplica identitats ni
resol encara duplicats/contaminació automàticament; veure document 30.
La selecció del gimnasta, la segmentació i l'API continuen pendents.
Els altres contractes avançats i les rutes API són propostes.
Els canvis de comportament hauran d'actualitzar el document afectat i, si canvien una frontera
o una decisió important, afegir un registre a `decisions/`.

## Lectura segons la tasca

Per construir el primer lector: 04, 05, 10 i 12. Per treballar el tracking: 03, 04, 06 i 07.
Per detectar salts: 04, 07, 08 i 12. Per integrar la plataforma: 04, 10 i 11.
El document 09 defineix l'extensió de puntuació, però no bloqueja el primer recorregut funcional.
