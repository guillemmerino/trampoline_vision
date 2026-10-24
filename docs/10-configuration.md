# 10. Configuració

## Tres nivells

| Tipus | Contingut | Exemple |
| --- | --- | --- |
| Model | Backend, tasca, pesos, dispositiu i sortida esperada. | [Font OpenPose enregistrada](../configs/models/openpose-recorded.example.json). |
| Escenari | Disciplina, captura, zona de treball i selecció del subjecte. | [Càmera fixa](../configs/scenarios/fixed-camera-trampoline.example.json). |
| Pipeline | Font de dades, components activats i artefactes. | [Reproducció](../configs/pipelines/replay-openpose.example.json). |

Els tres exemples de model/escenari/pipeline complet continuen com a disseny `0.1-draft`.
Hi ha una configuració executable independent: [inspect-openpose.json](../configs/pipelines/inspect-openpose.json),
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
La tria del tracker, el segmentador i els llindars queda pendent de les primeres proves.
