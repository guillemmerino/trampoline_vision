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

`recovery/fragments.json` i `fragments-disabled.json` són perfils executables
1.0 de la comanda independent inspect-fragments. La preparació està implementada;
el rematching fiable continua pendent. Els *.example.json 0.1-draft són només disseny
i es rebutgen en execució. Vegeu la [guia 29](../docs/29-recovery-fragment-inspection.md).

`experiments/recovery/` afegeix perfils executables explícits per `audit-recovery`
a 0.7.0. `experiments/detectors/` només registra receptes del pilot, sense
integrar inferència nova. Cap perfil experimental substitueix els defaults.
Vegeu la [guia 30](../docs/30-experimental-recovery-audit.md).
