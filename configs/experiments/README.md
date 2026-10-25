# Perfils i receptes experimentals

`recovery/*.json` són executables **només amb `audit-recovery --config ...`**.
No són valors per defecte ni reconstruccions validades. Inclouen controls
disabled/geometria i variants d'aparença del pilot, amb ID i revisió explícits.

`detectors/*.json` són receptes enregistrades, no un detector integrat ni
perfils acceptats per la CLI actual. La distinció és al camp
`implementation_status`. No modifiquen el detector original ni el tracker.

Els experiments es registren a
`benchmarks/studies/07-recovery-global/experiments.json`. Crear una revisió/perfil
nou quan canvien els criteris. Cada auditoria desa hash, còpia del perfil,
configuració efectiva, codi i inputs perquè les execucions anteriors no
depenguin del contingut futur del fitxer.

[Guia d'auditoria](../../docs/30-experimental-recovery-audit.md).
