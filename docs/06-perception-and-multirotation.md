# 06. Percepció, models i multirotació

## Responsabilitat

`perception` encapsula l'execució de models visuals. Un backend pot detectar persones, estimar
poses o oferir les dues capacitats. El tracker consumeix el contracte intern i no interpreta
la sortida nativa del backend. En reproducció de deteccions enregistrades no s'instancia cap model.

Canviar un model ja suportat s'ha de poder fer amb configuració. Incorporar un backend nou
requereix implementar i verificar el seu adaptador; editar un nom en JSON no resol diferències
d'esquema, preprocessament o semàntica. No hi ha cap backend d'inferència implementat encara.

## Contracte proposat d'adaptador

Declararà ID i versió, tipus de tasca, esquema de punts, suport CPU/GPU, pesos requerits,
transformacions d'entrada i informació de confiança disponible. La inicialització i l'alliberament
de recursos són explícits. La sortida s'associa als `FrameContext` rebuts i preserva fotogrames buits.
Una caixa derivada de pose no es presenta com si fos una detecció de persona independent.

Les dependències pesants són opcionals. La falta de pesos o d'una dependència genera un error
de configuració abans d'analitzar el vídeo, amb el backend afectat. La inferència no descarrega
pesos silenciosament. Les llicències del codi, pesos i dades s'han de revisar quan s'esculli el backend.

## Estratègia inicial de multirotació

S'adopta com una via de desenvolupament sense entrenament propi. Es proposen orientacions de
0, 90, 180 i 270 graus, configurables. La freqüència d'execució i una possible recuperació selectiva
queden obertes fins a mesurar cost i utilitat en els vídeos de trampolí.

Per cada orientació: preparar imatge, registrar transformació, executar backend i portar els
punts i caixes al fotograma original. Amb rotacions de 90/270 graus s'intercanvien dimensions.
Els tests han de cobrir cantonades, centre, límits i imatges no quadrades.

## Preparació i deduplicació

`preparation` valida formes, coordenades i validesa, i associa deteccions compatibles que poden
representar la mateixa persona en orientacions diferents. Inicialment convé comparar una política
que conserva el millor esquelet complet amb altres fusions. La similitud geomètrica no ha de
fusionar persones properes. La confiança entre orientacions no s'assumeix calibrada.

Si es fusionen punts de diverses deteccions, cal una hipòtesi comuna de persona i preservar la
procedència de cada punt. No es tria la millor articulació de tota l'escena independentment de
la seva identitat. Les observacions originals han de quedar disponibles per depurar.

## Restriccions pràctiques

Els crops han de conservar origen, padding, dimensions, escala i inversa exacta. Es proposa
preservar la relació d'aspecte quan el backend ho permeti; deformar a un quadrat sense declarar-ho
afecta la geometria. Una zona d'interès no s'ha de limitar al llit del trampolí si talla la fase
de vol. Els límits i la selecció de candidats requereixen proves.

## Dades heretades

Un ZIP fusionat sense origen per orientació entra com `legacy_fused`, amb procedència parcial.
La preparació pot estudiar duplicats, però no pot reconstruir angles absents ni suposar que totes
les deteccions provenen d'una única orientació. La nova inferència conservarà aquesta informació.
