# Configuració

`pipelines/inspect-openpose.json`, `visualize-openpose.json` i `track-openpose.json`
són executables (1.0). Tracking referencia la configuració de preparació i explicita
els paràmetres d'OC-SORT; veure la [guia 21](../docs/21-tracking-validation-guide.md).
Els exemples `design-only` continuen descrivint components futurs i la CLI els rebutja.

`preparation/pose-candidates.json` és una configuració de component implementada,
consumible des de Python amb `PreparationConfig.from_dict`; no és un pipeline de CLI.
Documentació a la [guia de preparació](../docs/20-pose-candidate-preparation.md).

Vegeu [configuració](../docs/10-configuration.md) i [execució CPU](../docs/15-cpu-replay-guide.md).

## Caixes i perfils (0.5.0)

`pipelines/track-boxes.json` és executable (2.0). `tracker_config` selecciona
un perfil de `trackers/`: OC-SORT, ByteTrack, BoT-SORT o BoT-SORT amb ReID.
Només l’últim referencia `models/osnet-msmt17.json`, amb pesos locals,
SHA-256, dispositiu i cache. Les rutes són relatives al fitxer que les declara.
Cap d’aquests fitxers no executa matching d’esquelets ni coherència de l’actor.
Veure la [guia 27](../docs/27-configurable-box-tracking.md).

`recovery/` conté únicament exemples `0.1-draft`, `design-only`, tots desactivats.
No són acceptats pel pipeline executable. El seu abast i pla d'implementació
s'expliquen al [document 28](../docs/28-recovery-package-design.md).
