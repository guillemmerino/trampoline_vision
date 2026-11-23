# Recovery

La preparació de fragments del tracking complet és executable a 0.6.0:
contractes, lectura validada, política consecutive_observations_v1, partició
de mostres i diagnòstic amb informe/JSONL i MP4 opcional.

A 0.7.0 `audit-recovery` afegeix costos geomètrics/aparença, hongarès global,
alternativa de no-unió, validació temporal i hipòtesis provisionals. Els senyals
de duplicats/contaminació només s'exporten per revisar. La resolució fiable
i la validació independent continuen obertes; apply no existeix.

[Disseny](../../../docs/28-recovery-package-design.md) · [Guia executable](../../../docs/29-recovery-fragment-inspection.md).

[Auditoria experimental](../../../docs/30-experimental-recovery-audit.md).

El [catàleg de casos per a recovery](../../../benchmarks/calibration/config/studies/recovery-case-catalog-v1.md)
recull les finestres de treball per avaluar l’auditoria de fragments
sobre la base experimental de velocitat simple.

`subject_path.py` conté el graf temporal experimental d’un sol subjecte.
El banc l’executa amb NumPy i una caixa inicial explícita per vídeo.
[Prova geomètrica i resultats](../../../benchmarks/calibration/config/studies/recovery-subject-path-v1.md).
