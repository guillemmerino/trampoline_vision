# 30. Recovery experimental en mode auditoria (0.7.0)

Estat: infraestructura executable de propostes globals, **sense apply ni garantia
d'identitat correcta**. Es continua estudiant com aconseguir recovery fiable.
No s'han canviat els perfils de tracking ni el detector per defecte.

## Frontera i execució

```text
tracking complet immutable + cache existent
  → fragments verificats
  → costos de geometria/aparença
  → hongarès global amb opció de no unir
  → hipòtesis i conflictes per revisar
```

La comanda nova és independent de `track` i `inspect-fragments`. Exigeix un
perfil explícit; no s'activa seleccionant un perfil del tracker. Els perfils
antics `configs/recovery/*.example.json` continuen sent esborranys rebutjats.

Exemple amb tracking canònic complet i FFprobe disponible:

```text
python -m trampoline_vision audit-recovery --tracking-report runs/tracking.json --config configs/experiments/recovery/global-geometry-v1.json --output runs/recovery-01.json
```

Amb aparença:

```text
python -m trampoline_vision audit-recovery --tracking-report runs/tracking.json --config configs/experiments/recovery/global-osnet-hungarian-v1.json --appearance-cache runs/cache/existing.sqlite3 --output runs/recovery-02.json
```

`--tracks`, `--video` i `--detections` permeten resoldre rutes traslladades
entre Docker i Windows. `--links-output` canvia el destí JSONL. Les sortides
han de ser noves. El perfil també queda protegit contra sobreescriptura.
No hi ha opció `--apply` ni reconstrucció publicada com a identitat validada.

La versió Docker s'ha de reconstruir després de canviar el paquet. La comanda
pot executar-se al servei CPU `replay`: no necessita carregar BoT-SORT o OSNet
per llegir les seves traces/descriptors ja calculats.

## Perfils experimentals

`configs/experiments/recovery/` conté perfils executables esquema 1.0,
`task: audit_tracking_recovery`, `mode: audit`, `status: experimental`:

| Perfil | Funció |
| --- | --- |
| `disabled-v1.json` | Valida/prepara però no associa ni inventa hipòtesis d'actor. |
| `global-geometry-v1.json` | Control geomètric, sense carregar aparença. |
| `global-osnet-hungarian-v1.json` | Referència experimental d'aparença, gap màxim 2 s i cost de no-unió .55. |
| `global-osnet-conservative-v1.json` | Sensibilitat al cost de no-unió .45. |
| `global-osnet-permissive-v1.json` | Sensibilitat al cost .65. |
| `global-osnet-long-gap-v1.json` | Sensibilitat a un gap màxim de 31 s. |

La resolució inclou tots els fragments en **una matriu del vídeo complet**.
El gap màxim limita arestes, sense tallar el vídeo en finestres independents.
Els descriptors mitjans, pesos, llindars i model de moviment són hipòtesis
experimentals. L'hongarès minimitza aquests costos, no l'error real d'identitat.

El perfil té `profile_id` i `revision`. Si canvia el comportament de la prova,
crear un perfil/revisió nou i actualitzar el manifest de l'estudi. Cada execució
desa els bytes identificats pel hash, una còpia del perfil i la configuració
efectiva amb els valors per defecte resolts. Això evita dependre d'un nom mutable.
L'esquema rebutja claus desconegudes, pesos incoherents, NaN i `mode: apply`.

`configs/experiments/detectors/` registra tres **receptes del detector** provades:
.02 sense tall per àrea, .05 sense tall i .05 amb les 20 caixes més grans.
Tenen `implementation_status: recorded_recipe_not_integrated_detector`:
documenten el pilot i **no són configuracions executables d'un detector nou**.
Es manté `max_det: 300` de YOLO; sense tall per àrea no vol dir sense cap límit.
El paquet actual continua llegint caixes enregistrades. El detector original
i els perfils estàndard no canvien.

## Cache i procedència

La CLI només accepta SQLite natiu, complet i tancat/checkpointed. Es llegeix
amb `mode=ro&immutable=1`; es rebutgen caches amb WAL pendent. No es completen
frames absents i no hi ha fallback a inferència. Cal conservar el cache que
va produir `track`, encara que el camí de l'informe provingui d'un contenidor.

Es comproven el hash del vídeo i les deteccions, la timeline, el fingerprint
registrat del model, els IDs/ordre/mesures de candidats, els checksums dels
vectors, les dimensions i la normalització. No es demanen els pesos ni
dependències del model per reutilitzar vectors existents. El fingerprint
identifica el model productor; no certifica que el model sigui apropiat per
al trampolí. Els informes antics sense hash original de vídeo porten un avís:
un hash calculat ara no demostra retroactivament els píxels originals.

Els NPZ del pilot extern requereixen l'importador explícit del benchmark 07.
No es poden passar directament com a cache SQLite ni com a informe de tracking.

## Costos i hipòtesis

`motion.py` calcula centres de caixa, escala mediana i velocitats de fins a
cinc observacions amb timestamps reals. Utilitza el mínim entre distància
de puntes i residus de predicció endavant/enrere; **no és un model balístic**.
La penalització temporal v1 és `min(1, gap_s / 2)`; el límit màxim d'aresta
és un paràmetre diferent. `appearance.py` compara vectors mitjans normalitzats.

`association.py` genera arestes dirigides, costos i alternatives locals,
amb columnes fictícies per no unir. Els enllaços no millors que no-unir no
s'escullen. Els `FragmentLink` escollits continuen amb estat `proposed`:
la raó diu `selected_by_optimizer_identity_unverified`, mai identitat acceptada.
Els costos i marges locals no són probabilitats ni confiança global calibrada.

La validació exigeix un predecessor/successor com a màxim, ordre temporal
estricte, absència de cicles/solapament i partició exacta de fragments.
Una hipòtesi referencia fragments originals, sense canviar observacions,
`track_id`, `candidate_id`, procedència o buits. No s'interpola dins dels buits.

`coherence.py` només assenyala possibles duplicats per solapament i salts
geomètrics interns. No resol duplicats, no divideix fragments i no certifica
coherència física de la cadena sencera. Els paràmetres d'aquests senyals són
heurístics v1: poden confondre dues persones superposades o un moviment real.

## Artefactes

- Informe JSON: IDs de run, perfil original/efectiu, versió i hashes del codi
  Python efectiu, inputs, cobertura, recomptes i hipòtesis provisionals.
- JSONL: tots els enllaços que superen les portes geomètriques, amb costos,
  elecció/rebuig i raons. Els recomptes de portes expliquen parelles no generades.
- Alternatives locals i senyals de revisió al JSON. No hi ha vídeo nou en aquesta
  comanda; `inspect-fragments` continua oferint diagnòstic visual i el pilot
  extern conserva el vídeo comparatiu.

L'informe declara `applied: false` i `identity_accuracy: not_evaluated`.
Els recomptes de cadenes no són mètriques de precisió. L'avaluació esportiva,
les referències d'identitat i la selecció del gimnasta no entren en els costos.
Les sortides es publiquen exclusivament, JSONL primer i informe al final,
amb rollback dels fitxers propis davant errors normals de publicació.

## Evidència i següents estudis

L'[estudi 07](../benchmarks/studies/07-recovery-global/README.md) registra
els experiments de confiança, el control complet i les associacions globals,
amb hashes i limitacions. No es presenta el pilot com a precisió validada.
Les proves comproven el solver, abstenció, contractes, procedència, cache
només lectura, preservació d'inputs, publicació i regressions existents.

Cal continuar estudiant duplicats, contaminació dins de fragments, coherència
d'identitat de cadenes, altres costos/algorismes i anotacions independents en
diversos vídeos. Aquests treballs continuen experimentals i no s'activa apply.

## Verificació de la integració

150 proves passen al runtime complet i amb la wheel 0.7.0 instal·lada.
A Windows passen119 i se n'ometen31 per capacitats opcionals absents.
La CLI sobre els930 frames i156 fragments reprodueix exactament les unions
dels sis perfils del pilot (inclòs disabled), preservant les dades i sense
inferència. Això comprova la integració, no la precisió de les identitats.
Evidència: `benchmarks/studies/07-recovery-global/integration-results.json`.
