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
