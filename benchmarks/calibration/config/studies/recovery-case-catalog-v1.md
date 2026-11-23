# Catàleg de casos per a recovery

El [manifest provisional](recovery-case-catalog-v1.json) fixa 18 finestres
contínues, sis per vídeo. Inclou 6 finestres centrades en buits, 6 en
transferències i 6 en continuïtat. Hi ha 1.052 fotogrames als clips i 118
fotogrames d’evidència visual seleccionats. Les àncores d’actor són
d’una primera revisió assistida i estan pendents de revisió humana
independent. La selecció deliberada d’episodis serveix per contrastar
comportaments concrets. Les freqüències del catàleg corresponen al disseny
de la mostra.

## Entrada congelada

Les assignacions són les de `velocity_soft_yolo` que va deixar
[l’estudi de confiança i silueta](trampoline-silhouette-v1.md). L’entrada
és el replay de YOLOv8m a 0,001, amb preparació representativa, zona central
`soft` i fins a 12 candidates per fotograma. La variant admet totes les
candidates per mantenir IDs confirmats, amb la confiança YOLO com a cost
suau. S’utilitzen els fitxers `botsort.frames.jsonl` de la comparació
anterior com a font de candidates congelades. Els IDs i les prediccions
provenen exclusivament de `velocity_soft_yolo`. El manifest fixa el SHA-256
de la traça, els originals i les candidates per vídeo. La generació de les
evidències llegeix els fitxers i els píxels originals.

## Casos que ha de distingir la revisió

| Vídeo | Buits | Transferències | Controls de continuïtat |
| --- | --- | --- | --- |
| AGE1 · `000905_31.0` | 174→191 a l’aire i 253→259 amb oclusió al llit | 29 passa a un jutge i 189 a un assistent | 29 al rebot i 189 durant una inversió |
| AGE2 · `000709_37.0` | 92 reapareix amb el mateix ID al voltant del 529 i 198→222 al final | 125 i 195 passen a dos assistents en finestres diferents | 36 durant el salt i 125 durant una inversió |
| AGE3 · `001351_19.0` | 26→60 durant el salt i 117→145 amb oclusió al llit | 0 passa a la graderia i 60 a un assistent | 82 reapareix amb el mateix ID i segueix durant una altra inversió |

Cada finestra té un objectiu principal. Pot incloure episodis d’un altre
tipus. Alguns IDs, com el 189 d’AGE1 o el 125 d’AGE2, tenen un tram útil i
un altre de contaminat. Qualsevol proposta d’enllaç s’avalua entre trams
d’actor identificat. Per exemple, a AGE2, al 534, les caixes associades a
92 i 89 són útils per al mateix gimnasta. A AGE3, al 97, la caixa del 26
cau sobre la zona dels jutges mentre el gimnasta és visible fora de la
caixa. El 26 torna a donar suport al gimnasta al 99.

A AGE1, l’ID 29 és del gimnasta al 275 i torna a seguir-lo al 295. Al 280
segueix un jutge. Els extrems mantenen el mateix número amb una
transferència entremig. Hi ha dos
[exemples visuals seleccionats](../../reviews/recovery-case-catalog-v1/README.md)
al repositori.

## Revisió independent

1. Per cada MP4, mira primer la columna de l’original. Assigna una
   referència pròpia al gimnasta del vídeo i mantén-la entre salts i
   oclusions. Revisa els fotogrames en ordre. Els IDs del tracker són
   locals a cada vídeo i queden a la columna central.
2. A la tercera columna, marca totes les candidates útils. Una caixa gran
   o parcial serveix si permet localitzar el gimnasta amb claredat.
   Usa `useful`, `no_useful_candidate` o `ambiguous` per fotograma.
   En cas d’oclusió, registra també si el gimnasta és visible, parcialment
   visible o ocult. El número dibuixat a la tercera columna és el sufix
   de `candidate_id`. A `review-frames.jsonl` hi ha l’ID complet i la
   geometria, incloses les candidates que queden sense assignar.
3. Contrasta les candidates útils amb `observed`. Una candidata útil
   sense ID és una oportunitat d’associació. Si cap candidata útil té ID,
   hi ha un buit d’observació del gimnasta. `predicted_ids` registra els
   IDs que el tracker manté només com a predicció en aquell fotograma.
   Marca per separat les caixes mixtes i els IDs assignats a assistent,
   jutge o públic.
4. Identifica els trams del gimnasta, els intervals de transferència i
   el primer i últim fotograma decidible. Si el mateix ID reapareix
   després d’un buit, compta continuïtat entre els extrems i conserva el
   buit al registre. Si l’ID canvia, contrasta la possible unió entre
   trams nets. Si també canvia l’actor, aïlla el tram contaminat. Contrasta
   després les anotacions independents amb les àncores i els intervals
   `unresolved` del manifest.

Desa la teva passada en un fitxer a part, amb qui ha revisat i la data.
Per fotograma, registra `window_id`, `frame_index`, `visibility`,
`candidate_status`, `useful_candidate_ids`, `ambiguous_candidate_ids`,
`gymnast_track_ids` i `other_actor_track_ids` amb el rol. Per episodi,
desa `window_id`, el tram anterior i posterior amb el rol i l’ID,
l’interval incert i la decisió que proposaries a recovery. Les finestres i
els intervals del manifest comencen al primer índex i exclouen l’últim.
Un `track_id: null` a una àncora indica que la primera revisió no hi ha
identificat cap observació útil del gimnasta. La disponibilitat de
candidates es decideix amb el quadre complet de la tercera columna i la
traça. Les discrepàncies entre revisors queden com a ambigüitat fins
que es resolguin.

## Reserva

Queden reservats per contrastar resultats de recovery
`JPN_AGE_1_001107_32.0`, `JPN_AGE_2_000137_26.0` i
`JPN_AGE_3_001501_28.0`, un vídeo per grup. El catàleg en fixa els
originals i la selecció s’ha fet pel manifest del corpus, fora de les
seleccions anotades consultades. Els seus píxels i tracks queden fora
d’aquesta iteració. La reserva és específica de l’estudi de recovery.

## Reproducció

Des de l’arrel del repositori, amb Docker, la imatge de calibratge
`trampoline-vision:calibration-gpu-v1`, el corpus local
`data/calibration-v1` i els runs congelats
`trampoline-silhouette-v1` i `identity-continuity-v1`.

```bash
docker run --rm --network none --entrypoint python \
  --user "$(id -u):$(id -g)" \
  -e PYTHONPATH=/workspace/src:/workspace -e PYTHONDONTWRITEBYTECODE=1 \
  --mount "type=bind,src=$PWD,dst=/workspace,readonly" \
  --mount "type=bind,src=$PWD/runs/calibration,dst=/results" \
  -w /workspace trampoline-vision:calibration-gpu-v1 \
  -m benchmarks.calibration.tools.review_recovery_cases \
  benchmarks/calibration/config/studies/recovery-case-catalog-v1.json \
  --output /results/recovery-case-catalog-v1-review --clips --show-candidates
```

El directori de sortida ha de ser nou. La comanda deixa un MP4 i una
làmina JPG per finestra. `review-frames.jsonl` dona la traça contínua
amb candidates, observacions, IDs predits, temps i decisions de la base.
Les superposicions no dibuixen prediccions. `completed.json` registra
la procedència i les empremtes del catàleg, el codi i les sortides. Els
artefactes de la primera passada són a
`runs/calibration/recovery-case-catalog-v1/` i ocupen aproximadament 50 MiB.
La primera passada va utilitzar la imatge local
`sha256:96f1796b900083d68831101bfc0a171685d5695d64547e4a226f0086017f64a7`
amb descodificació per CPU.
