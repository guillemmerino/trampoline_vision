# 14. Guia de desenvolupament

## Estat de l'esquelet

Python >= 3.10, distribució `trampoline-vision`, import `trampoline_vision`, estructura `src/`.
El nucli no té dependències d'execució. El backend de construcció és setuptools >= 61.
La versió es declara a `trampoline_vision.__version__` i es reutilitza a les metadades del paquet.
Ja hi ha l’executable `trampoline-vision inspect` i l’entrada `python -m trampoline_vision`; no hi ha endpoints.

## Primera implementació recomanada

Començar pels contractes mínims de `FrameContext`, esquema de punts i detecció; després manifest,
lector enregistrat i una sortida de revisió. Introduir una dependència només si hi ha un consumidor
concret. Les llibreries de lectura de vídeo, arrays o models s'escolliran quan s'implementi la
capacitat que les necessita. Un backend GPU serà una dependència opcional.

La configuració `inspect-openpose.json` i el manifest 1.0 tenen carregadors; els exemples `design-only` requereixen components futurs. No s'ha de crear una CLI
que accepti els fitxers i retorni èxit sense executar cap anàlisi. Un component pendent ha de
produir un missatge explícit fins que existeixi una implementació real.

## Convencions

Mòduls i identificadors de codi en anglès; documentació de producte en català. Unitats en els
noms quan sigui útil (`timestamp_s`, `duration_s`). Tipus i errors explícits a les fronteres.
Evitar inferir esquemes per la divisibilitat d'un vector o per l'ordre accidental de columnes.
Els `__init__.py` no han de tenir efectes laterals ni reexportar dependències visuals pesants.

Les funcions de domini reben dades i configuració; no resolen directoris globals, no consulten
HTTP i no creen gràfics de depuració automàticament. Les eines de diagnòstic s'activen i escriuen
en un directori d'execució, sense sobreescriure entrades.

## Proves i documentació

Afegir proves quan hi hagi comportament real, especialment sobre errors d'índex, transformacions,
buits, identitat i límits. Les fixtures han de ser petites i documentades. No versionar vídeos
grans, pesos o fitxers temporals per facilitar un test.

Actualitzar el contracte i els exemples quan canviï una frontera. Les decisions rellevants es
registren com ADR a `docs/decisions/`. Els resultats experimentals expliquen dades utilitzades,
configuració, mètriques i limitacions; no es traslladen al paquet només perquè funcionin en un clip.

## Entorn local i dades

Les instruccions bàsiques d'instal·lació són al [README](../README.md). Per treballar sense GPU,
utilitzar deteccions enregistrades i evitar imports de backends d'inferència. Les rutes del cas
inicial es resolen des del manifest; no es copien a constants del codi.

El directori `data/` és local i està exclòs del control de versions, excepte README i manifests
d'exemple. Els experiments tampoc no importen ni modifiquen els scripts de TFM. Si s'adapta una
idea, se'n documenta l'origen i es comprova sobre els nous contractes.

## Documentació dins del codi

Cada mòdul, classe, funció i mètode ha de tenir una docstring en català que expliqui el seu paper
i el motiu de la separació. Quan sigui rellevant, ha d'indicar entrades, retorn, errors i efectes
sobre fitxers o processos. Els noms del codi es mantenen en anglès. Els comentaris de camps expliquen
unitats, identitat i absències; els de blocs expliquen decisions que no resulten evidents del codi.
Les proves també expliquen quin comportament o regressió protegeixen. No s'afegeixen comentaris
que es limitin a repetir una assignació. Vegeu la [guia de lectura](16-code-reading-guide.md).

## Decisió pendent

Les proves inicials utilitzen `unittest` de la biblioteca estàndard. No s’ha escollit gestor de lockfiles, linter, servei HTTP ni cua. Es fixaran
quan s'introdueixi el primer comportament executable, conservant una instal·lació mínima del nucli.
