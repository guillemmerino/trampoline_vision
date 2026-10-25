# 26. Comparació amb aparença visual i recuperació d'identitat

Estudi 05, executat el 25 d'octubre de 2026. Protocol i scripts a
[`benchmarks/studies/05-reid`](../benchmarks/studies/05-reid/README.md).

## Resultat i decisió

Afegir aparença visual redueix els canvis mínims d'identitat als instants
revisats dels tres clips. La millora és més clara al cas inicial: es resol
el contraexemple del jutge als fotogrames 300, 360 i 390 i una mateixa
identitat acumula més matches del gimnasta. Encara hi ha fragmentació,
bretxes de detecció i associacions dubtoses al contacte amb assistents.

BoT-SORT amb ReID queda com a candidat per continuar l'experimentació.
No es declara una trajectòria completa validada ni s'incorpora com a
backend de producció en aquest increment. En dos dels tres clips hi ha
una observació revisada menys que amb OC-SORT: menys canvis d'ID no
equivalen, automàticament, a més cobertura.

## Què s'ha comparat

Tres variants sobre les mateixes deteccions, tots els actors i tots els
fotogrames des de zero:

1. OC-SORT del paquet 0.4.0: baseline existent.
2. BoT-SORT sense ReID: control del canvi d'algoritme i de la implementació.
3. El mateix BoT-SORT amb ReID: control de l'aportació de l'aparença.

S'utilitza BoxMOT 16.0.9 amb l'API de deteccions NumPy fixada, OSNet
`osnet_x0_25_msmt17.pt`, PyTorch 2.5.1 CPU i Torchvision 0.20.1 CPU.
La versió de distribució de BoxMOT és 16.0.9; el seu `__version__` intern
imprimeix 16.0.8. La comprovació de compatibilitat utilitza les metadades
de la distribució, no el text de log.

Els pesos provenen del model de reidentificació de persones publicat al
[model zoo d'OSNet](https://kaiyangzhou.github.io/deep-person-reid/MODEL_ZOO.html).
La combinació d'aparença i moviment es descriu a
[BoT-SORT](https://arxiv.org/abs/2206.14651); la integració fixada s'ha
inspeccionat a la [wheel BoxMOT 16.0.9](https://pypi.org/project/boxmot/16.0.9/).
BoxMOT es distribueix sota AGPL-3.0 i es manté separat del paquet en aquest estudi.

No s'ha entrenat cap model ni s'ha tornat a executar YOLO o OpenPose.
Els fotogrames originals només s'han usat localment per inferir descriptors
ReID. Cada retall de caixa es normalitza a 256 × 128, passa de BGR a RGB,
s'estandarditza amb els valors del backend i produeix un descriptor de
512 components normalitzat. No s'han afegit rotacions al descriptor.

S'ha verificat el SHA-256 dels pesos i que els 565 tensors del backbone
carregat coincideixen exactament amb el checkpoint; el classificador de
persones del conjunt d'entrenament no s'utilitza per associar els vídeos.

## Entrades i condicions comunes

| Cas | Fotogrames | Durada | Caixes enregistrades |
| --- | --- | --- | --- |
| `JPN_AGE_1_000905_31.0` | 930 | 31 s | 18.600 |
| `JPN_AGE_1_001814_34.0` | 1.020 | 34 s | 20.400 |
| `JPN_AGE_3_001351_19.0` | 570 | 19 s | 11.400 |

Tots tenen 30 FPS i 960 × 1080 píxels. S'han contrastat PTS, recompte i
dimensions de cada fotograma descodificat amb ffprobe. Els SHA dels vídeos,
CSV, pesos i protocol queden registrats. Les anotacions de candidat només
s'accepten amb els mateixos SHA de vídeo i CSV, perquè `det_id` es reinicia
a cada fotograma i no és una identitat temporal.

La confirmació pública exigeix tres matches forts consecutius, confiança
≥ 0,1. BoT-SORT admet confiança > 0,02 per mantenir un ID confirmat, però
els matches febles no confirmen naixements. El control sense ReID i el
control amb ReID comparteixen tots els altres paràmetres. Les comparacions
amb OC-SORT també inclouen diferències de tracker i d'admissió feble; el
contrast directe de l'aparença és entre les dues variants BoT-SORT.

La compensació del moviment de càmera s'ha substituït per una transformació
identitat explícita, adequada a la hipòtesi de càmera fixa. El llindar
espacial equival a exigir IoU aproximadament 0,1 en l'associació principal;
els valors exactes, incloent aparença, són a `protocol.json`.

El buffer BoT-SORT és nominalment de 15 fotogrames. En aquesta API, la
llista pública `lost_stracks` pot retenir un ID un tick addicional. El
port segueix les llistes que el backend encara pot associar; l'auditoria
registra buits de fins a 16 fotogrames abans d'acabar l'ID. No és una
garantia estricta d'expiració a 0,5 s. Aquesta frontera requeriria una
política explícita abans d'una integració de producció.

## Referències visuals i mètriques

S'han revisat 178 instants del vídeo original amb deteccions però sense
mostrar inicialment les sortides dels trackers: 106, 34 i 38 per cas.
El primer cas combina mostreig cada 15 fotogrames i tres finestres denses
de fallades ja conegudes; els altres es mostregen cada 30 i 15 fotogrames.

Les referències indiquen quines deteccions corresponen al gimnasta i
admeten diverses caixes duplicades de la mateixa persona. No mesuren la
precisió de l'extensió corporal ni la qualitat de les articulacions.
Les caixes ambigües per superposició s'exclouen de la mètrica principal.
Un fotograma sense cap candidat del gimnasta continua comptant com a buit
observat: una predicció no es converteix en detecció.

Durant el control de qualitat es va detectar una referència que apuntava
a l'assistent del primer pla i diverses caixes duplicades no incloses.
S'han conservat la referència inicial, l'anàlisi inicial, set correccions
explícites i la revisió definitiva. La revisió 2 es va fer amb resultats
ja visibles: no és cega ni independent. Totes les variants s'han recalculat
amb la mateixa revisió. La conclusió qualitativa es manté en les dues versions.

`minimum_id_changes_between_reviewed_matches` calcula el mínim nombre
de canvis possible entre els conjunts d'IDs acceptables, per no penalitzar
arbitràriament duplicats simultanis. És un límit inferior en instants
revisats, no el nombre real de canvis durant tot el vídeo.

Resultats definitius, amb revisió 2:

| Cas | Variant | Matches observats / elegibles | IDs diferents als matches | Canvis mínims entre matches |
| --- | --- | --- | --- | --- |
| 000905 | OC-SORT | 76/89 | 18 | 17 |
| 000905 | BoT-SORT sense ReID | 81/89 | 12 | 11 |
| 000905 | BoT-SORT amb ReID | 79/89 | 9 | 7 |
| 001814 | OC-SORT | 23/29 | 14 | 12 |
| 001814 | BoT-SORT sense ReID | 22/29 | 9 | 7 |
| 001814 | BoT-SORT amb ReID | 22/29 | 9 | 6 |
| AGE 3, 001351 | OC-SORT | 26/33 | 11 | 11 |
| AGE 3, 001351 | BoT-SORT sense ReID | 27/33 | 10 | 10 |
| AGE 3, 001351 | BoT-SORT amb ReID | 25/33 | 8 | 7 |

S'exclouen 17, 5 i 5 instants ambigus respectivament. Dins dels elegibles,
4, 1 i 4 instants no tenen cap caixa enregistrada del gimnasta. Els IDs
diferents també inclouen alguns tracks duplicats; no s'han de llegir tots
com a fragments temporals consecutius. No hi ha HOTA, MOTA, IDF1 o una
afirmació de precisió global perquè falta una anotació densa independent.

## Què s'ha resolt i què encara falla

Al primer clip, l'ID dominant d'OC-SORT coincideix amb el gimnasta en
25 instants elegibles; el de ReID, en 56. Als fotogrames 300, 360 i 390,
OC-SORT segueix la fila de jutges i ReID manté el gimnasta.

L'ID ReID `botsort_reid:1` perd observacions als fotogrames 310–311 i
es recupera al 312 amb el mateix ID. Als fotogrames 474–475 torna a tenir
un buit i es recupera al 476. El fotograma 475 no conté cap caixa del
gimnasta al CSV: l'estimació del tracker no resol aquesta falta de mesura.

Després del contacte proper al llit al voltant dels fotogrames 486–491,
l'ID deixa de recuperar el gimnasta. A 495 és predit i al 508 ja ha acabat;
altres IDs representen l'actor més endavant. La prova ha millorat una
fallada concreta, però no ha aconseguit una identitat durant tot el clip.

El diagnòstic de descriptors purs recupera la detecció correcta com a veí
visual més proper en 56/84, 19/27 i 13/28 parells revisats de la revisió 2.
Aquests nombres són diagnòstic de recuperació de descriptors entre instants,
no precisió del tracker. Indiquen que l'aparença preentrenada també és
ambigua, especialment amb canvis grans de postura i persones petites.

## Cost i preparació per refinar

Amb CPU i quatre fils, l'extracció dels descriptors va trigar aproximadament
326, 282 i 173 segons. Cada passada d'associació va trigar entre 2 i 7
segons per clip. Són temps d'aquest equip i d'aquest entorn, sense estimar
rendiment GPU ni servei de producció. Codificació i descàrrega no hi entren.

Els descriptors s'han desat amb offsets de candidat, SHA i versions. El
replay amb `--reuse-embeddings-from` permet canviar paràmetres d'associació
sense repetir inferència. Rebutja canvis de vídeo, deteccions, pesos o
runtime de preprocessament. S'han repetit les nou execucions amb el cache
i s'ha verificat igualtat exacta dels registres excepte el UUID de l'execució.
El Dockerfile té 61 restriccions de versió capturades de l'entorn real.

## Artefactes i comprovacions

Arrel local: `runs/tracking-reid-study-05/`.

- `summary.json`, `protocol.json`, `environment.txt`: procedència, versions i cost.
- `analysis.json`: pilot amb referències inicials; `analysis-reviewed.json`:
  revisió 2 usada als vídeos; `analysis-final.json`: mateixes mètriques i
  validació afegida de la vinculació dels inputs.
- `recovery-audit.json`: buits del mateix ID i els tres contraexemples del jutge.
- Per cas: tres `*.frames.jsonl` complets i `embeddings.npz` verificat.
- Per cas, `review-output-v2/comparison.mp4`: OC-SORT a l'esquerra i ReID a
  la dreta, tots els actors, mesures i prediccions distingides.
- Per cas, `review-output-v2/*.trajectories.csv`: trajectòries de totes
  les identitats dels tres trackers, amb estat i evidència explícits.
- Per cas, `review-output-v2/report.json`: PTS, dimensions, recomptes i SHA
  de la referència i l'anàlisi que s'han utilitzat per dibuixar.
- `review/`: làmines originals, control de referències i previsualitzacions.

Els IDs ressaltats són una selecció manual fixa per diagnòstic. No hi ha
selector automàtic del gimnasta, unió d'IDs, articulacions fabricades ni
suavitzat de centres. El centre d'una caixa no és el centre de massa.
Les exportacions preliminars es conserven a `review-output/`.

S'han superat les 95 proves existents en l'entorn ReID i els controls
sintètics del nou port: naixement fort, actualització feble, pèrdua,
recuperació, expiració, candidats reordenats i preservació de caixes.
OC-SORT reprodueix exactament el baseline complet de l'estudi 04.
Els tres vídeos comparatius tenen recompte, dimensions i cada PTS verificats.
El codi, protocol, restriccions i resultats petits es versionen; vídeos,
descriptors i pesos queden a `runs/`.

## Següent treball justificat per aquest resultat

Prioritzar els contactes amb assistents i les inversions que encara
fragmenten el seguiment. El cache permet comparar una hipòtesi cada vegada:
geometria de recuperació, exclusió temporal d'actualitzacions d'aparença
amb caixes mixtes i representació visual davant grans canvis d'orientació.
Cal mantenir el control sense ReID i ampliar la revisió independent.

L'associació amb poses globals independents pot aportar evidència addicional,
però no s'ha executat en aquest estudi. La segmentació i la puntuació
continuen pendents d'una trajectòria i una qualitat articular validades.
