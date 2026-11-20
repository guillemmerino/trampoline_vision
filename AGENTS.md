# Convencions de treball del repositori

Aquestes convencions s’apliquen als canvis futurs de codi, proves i documentació.

## Estructura i responsabilitats

- `src/trampoline_vision/`: implementació reutilitzable de producció, separada per dominis. Els experiments consumeixen aquest codi; no en mantenen còpies alternatives actives.
- `configs/`: configuracions executables de l’aplicació. Un perfil experimental o un resultat prometedor no és automàticament un valor per defecte validat.
- `benchmarks/calibration/`: eines compartides, anotacions i proves de calibratge. Comença pel seu `README.md`.
- `benchmarks/calibration/archive/`: plans, resultats seleccionats i informes d’estudis tancats. No els presentis com a configuracions actives.
- `runs/`, `data/`, pesos i caches: artefactes locals segons `.gitignore`; no versionis bateries completes ni dades grans.
- Cada carpeta amb una responsabilitat nova ha de tenir un punt d’entrada que expliqui què conté i quan s’utilitza. Evita scripts solts i noms successius com `final2` o `nou-definitiu`.

## Llegibilitat i llengua

- Escriu en català els comentaris, docstrings i explicacions tècniques nous o modificats. Conserva els identificadors del codi en anglès quan sigui la convenció existent.
- Cada mòdul nou ha d’explicar la seva responsabilitat. Cada classe i funció nova ha de tenir un docstring que indiqui què fa; explica entrades, retorns, efectes i límits quan no siguin evidents. Una funció senzilla només necessita una frase útil.
- Els comentaris han d’explicar decisions, invariants i motius. No repeteixis literalment el codi.
- Conserva la procedència de les dades i distingeix originals, candidats derivats, observacions i prediccions.
- No reescriguis dades, scripts capturats o metadades històriques només per traduir-los o modernitzar-ne els noms. Documenta que són captures congelades.

## Estudis i documentació

- Una prova nova ha de tenir inputs explícits, configuració registrada, sortida identificable i instruccions per revisar-la en una iteració independent.
- Els plans nous en curs van a `benchmarks/calibration/config/studies/`. Els tancats s’agrupen a `archive/<estudi>/`, amb un README, estat, conclusió, limitacions i enllaços a evidències.
- Conserva en Git una selecció petita de resums i casos visuals que fonamentin les conclusions. Els registres complets i vídeos generats van a `runs/`.
- Les referències d’IA continuen provisionals fins que hi hagi validació humana explícita; no les reetiquetis per inferència.
- Indica denominadors i abast. Una mostra de fotogrames no valida tot el vídeo; una discrepància geomètrica no confirma per si mateixa una pèrdua del gimnasta.

## Canvis d’estructura i verificació

- Quan moguis fitxers, actualitza els imports, les rutes relatives, les comandes, els tests i els enllaços de documentació afectats.
- Mantén la integritat dels artefactes congelats. Si una ruta executable canvia, explica que la identitat del pla/codi canvia i que no s’ha de reprendre sobre una execució antiga.
- Executa les comprovacions adequades al canvi. Per reorganitzacions del banc, comprova la navegació, la resolució dels plans, la integritat d’evidències i les comandes amb preflight quan existeixi.
- No executis una bateria costosa per comprovar només un canvi de noms o documentació.
