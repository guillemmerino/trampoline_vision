# 10. Configuració

## Tres nivells

| Tipus | Contingut | Exemple |
| --- | --- | --- |
| Model | Backend, tasca, pesos, dispositiu i sortida esperada. | [Font OpenPose enregistrada](../configs/models/openpose-recorded.example.json). |
| Escenari | Disciplina, captura, zona de treball i selecció del subjecte. | [Càmera fixa](../configs/scenarios/fixed-camera-trampoline.example.json). |
| Pipeline | Font de dades, components activats i artefactes. | [Reproducció](../configs/pipelines/replay-openpose.example.json). |

Els tres exemples de model/escenari/pipeline complet continuen com a disseny `0.1-draft`.
La configuració d’inspecció executable és: [inspect-openpose.json](../configs/pipelines/inspect-openpose.json),
amb `schema_version: 1.0`, `task: inspect_recorded_detections`, `case_manifest` i
`missing_frames_policy` (`report` o `error`). El carregador rebutja claus desconegudes i pipelines
de disseny. El manifest 1.0 també s’ha implementat; encara no hi ha un JSON Schema formal.

## Resolució proposada

Una ruta de configuració relativa a un fitxer es resol respecte d'aquell fitxer. Les rutes internes
d'un manifest també es resolen respecte de la seva carpeta. No es depèn del directori des d'on
s'invoca la futura CLI. Els manifestos d'exemple inclouen un `path_base` explícit.

Ordre proposat: valors per defecte del component, fitxers model/escenari/pipeline i overrides
explícits admesos per la interfície. Les opcions d'infraestructura —per exemple ubicació de
treballs— poden venir de l'entorn, però els llindars d'anàlisi no canvien silenciosament per
variables globals. Els conflictes s'han de detectar, no resoldre amb una fusió arbitrària.

## Validació abans d'executar

Comprovar versió, components existents, fitxers d'entrada, compatibilitat de punts, dispositiu,
pesos, orientacions i necessitats dels consumidors. Un component marcat `unselected` als exemples
és una decisió pendent i haurà de produir un error accionable, no un fallback aleatori.

`null` en una zona d'interès significa que no n'hi ha cap de configurada; no és una zona de mida
zero. Les polítiques automàtiques de selecció o les propietats que el sistema pugui inferir s'han
de declarar expressament. L'absència d'una opció requerida no activa una heurística amagada.

## Configuració efectiva i reproducció

Cada execució desa una còpia resolta: components i versions, paràmetres, manifest utilitzat,
referències d'entrada i identificador de pesos quan existeixin. Les credencials no s'inclouen en
els artefactes ni logs. Quan sigui viable es registraran hashes dels inputs o una identitat
immutable equivalent. No es tria el model per data de modificació d'un directori.

## Evolució

El primer carregador ha de ser petit i estricte. No cal construir un sistema de plugins externs
abans del primer adaptador, però el registre de backends ha de quedar centralitzat. Els canvis
de configuració requereixen documentar-ne migracions quan canviïn el significat d'una opció.
El primer backend de tracking és OC-SORT de trackers 2.6.1. Segmentador i llindars
de seguiment continuen pendents de proves.

## Preparació de candidats des de Python

`configs/preparation/pose-candidates.json` és una configuració de component 1.0,
amb seccions `box` i `deduplication`. La valida `PreparationConfig.from_dict` després
de la lectura JSON estricta. Les claus desconegudes es rebutgen i els camps omesos
es resolen amb defaults. La deduplicació està desactivada inicialment.
No és per si sola una configuració de pipeline; `track-openpose.json` la referencia. Opcions i ús a la
[guia 20](20-pose-candidate-preparation.md).

## Tracking executable

`configs/pipelines/track-openpose.json` utilitza schema 1.0 i task
`track_recorded_detections`. Resol `case_manifest` i `preparation_config` respecte
del mateix fitxer i valida `tracker` i `missing_frames_policy`. Només hi ha backend
`ocsort`; noms desconeguts i errors de claus es rebutgen. El fitxer no activa
cap inferència visual. Rang temporal i rutes de sortida s'indiquen per CLI.
L'informe desa tots els defaults resolts i el pressupost temporal efectiu.
Veure [guia 21](21-tracking-validation-guide.md).

## Visualització executable

`visualize-openpose.json` utilitza schema 1.0 i task `visualize_recorded_detections`.
Comparteix `case_manifest` i `missing_frames_policy` amb inspecció. `render` admet
`view`, `min_confidence`, `min_visible_points` i `show_labels`; les opcions explícites de CLI
hi prevalen. Els intervals `--start` i `--end` es donen per terminal. Vegeu la
[guia de visualització](17-visualization-guide.md).
