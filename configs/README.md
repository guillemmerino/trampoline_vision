# Configuració

`pipelines/inspect-openpose.json`, `visualize-openpose.json` i `track-openpose.json`
són executables (1.0). Tracking referencia la configuració de preparació i explicita
els paràmetres d'OC-SORT; veure la [guia 21](../docs/21-tracking-validation-guide.md).
Els exemples `design-only` continuen descrivint components futurs i la CLI els rebutja.

`preparation/pose-candidates.json` és una configuració de component implementada,
consumible des de Python amb `PreparationConfig.from_dict`; no és un pipeline de CLI.
Documentació a la [guia de preparació](../docs/20-pose-candidate-preparation.md).

Vegeu [configuració](../docs/10-configuration.md) i [execució CPU](../docs/15-cpu-replay-guide.md).
