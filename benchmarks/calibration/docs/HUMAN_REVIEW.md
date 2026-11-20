# Revisió humana de l’anotació i de YOLO

La pàgina preparada és a
`runs/calibration/expanded-localization-v1/human-review/index.html`.
Inclou els **1.440 fotogrames originals** i totes les candidates de les dues
variants de YOLO, també als 173 casos exclosos de l’avaluació original.
No executa inferència ni modifica els resultats o anotacions originals.

## Obrir amb desat automàtic al projecte

```bash
cd /home/tics/personal/trampoline-vision
python3 -B -m benchmarks.calibration review serve
```

Obre `http://localhost:8766/`. Si treballes amb VS Code per SSH, reenvia el port
**8766** al panell **Ports**. El servidor només escolta a `127.0.0.1`.

Cada canvi es desa automàticament a
`runs/calibration/expanded-localization-v1/human-review/review-state.json`.
Es manté un historial de canvis a `history/`. El missatge «Desat al servidor»
confirma que ja està disponible per a l’agent. Es pot tancar i tornar a obrir
la mateixa pàgina. Les pestanyes amb una revisió antiga no poden sobreescriure
silenciosament els canvis d’una altra pestanya.

## Què valorar

1. **Presència:** el gimnasta és visible, no és visible, o és indeterminat/ocult.
2. **Anotació:** aprova la caixa groga, rebutja-la, indica que falta o deixa-la
   pendent. Si cal, activa «Dibuixa / corregeix caixa» i arrossega sobre la imatge.
3. **YOLO:** selecciona una candidata clicànt-la a la imatge o amb el selector.
   Marca-la suficient, parcial però útil o incorrecta. «Cap caixa útil» rebutja
   el conjunt de candidates del detector; rebutjar una candidata sola no implica
   que les altres també siguin dolentes.

Per a la fase de tracking de caixes, «suficient» prioritza mantenir el gimnasta
localitzat: una caixa amb marge o temporalment més gran pot ser útil encara
que els seus límits no coincideixin amb l’anotació. Si inclou un assistent,
registra-ho a les notes; això no autoritza a transferir-li l’ID. La reconstrucció
i l’associació dels esquelets són posteriors. Els veredictes anteriors es
conserven tal com es van registrar, sense reinterpretar-los automàticament.

El **cian** és la candidata seleccionada; el **groc** és l’anotació original;
el **rosa** és la correcció nova. Les dues pestanyes permeten valorar 0,001 i
0,002 separadament. La selecció inicial per IoU és només una ajuda visual:
**no és una aprovació humana automàtica**. Escollir una altra candidata tampoc
no la dona per bona; cal prémer el veredicte corresponent.

Pots donar YOLO per bona encara que no hi hagi anotació. Per afegir geometria
a l’anotació pots dibuixar-la o usar «Usa la YOLO seleccionada». En el segon
cas es registra que la caixa prové del detector: és una validació humana assistida
per YOLO, **no una referència independent del detector**.

El filtre inicial prioritza discrepàncies i exclusions. «Tots els fotogrames»
permet revisar també els que ja superaven IoU 0,5. Hi ha filtres per vídeo,
fotograma i decisions pròpies, zoom, vista de l’original i comentaris.
«Deixa pendent» permet retirar un veredicte. Els veredictes són independents
entre anotació i detector; no s’aproven la resta de fotogrames d’un vídeo.

## Còpia de seguretat i mode sense servidor

«Exporta decisions» descarrega un JSON vinculat als SHA dels inputs d’aquesta
prova. «Importa decisions» el recupera i conserva les altres decisions locals;
els fotogrames coincidents se substitueixen només després de confirmar-ho.

Si obres l’HTML directament o amb un servidor estàtic, es desa una còpia al
navegador i es mostra explícitament aquest mode. **En aquest cas cal exportar
el JSON i facilitar-lo a l’agent:** l’agent no pot llegir el localStorage del
teu navegador. La carpeta amb l’HTML, CSS, JS i `images/` ha de conservar-se junta.

## Recalcular la valoració quan hi hagi decisions

Sense GPU, vídeos ni pesos:

```bash
python3 -B -m benchmarks.calibration review assess \
  --output runs/calibration/expanded-localization-v1/human-assessment-v1
```

La comanda llegeix el `review-state.json` del servidor. Per usar un JSON exportat:

```bash
python3 -B -m benchmarks.calibration review assess \
  --decisions /ruta/a/decisions-exportades.json \
  --output runs/calibration/expanded-localization-v1/human-assessment-v2
```

Cal triar un output nou per conservar les valoracions anteriors. Es genera
`ASSESSMENT.md`, `result.json`, `samples.csv` i una còpia de les decisions usades.

La revaloració separa la **cobertura geomètrica** de la **utilitat confirmada
humanament**. Les anotacions rebutjades sense correcció deixen de ser una caixa
geomètrica vàlida; els casos visibles sense anotació poden tenir una detecció
humana suficient/parcial, però no una IoU inventada. Les caixes sense revisar
conserven la procedència provisional d’IA i les decisions antigues només es
conserven automàticament si la geometria no ha canviat.

Les decisions es vinculen al paquet exacte, vídeo, fotograma, variant i candidata
guardats. No es poden reutilitzar silenciosament amb altres inputs.

## Preparar una altra còpia

```bash
python3 -B -m benchmarks.calibration review prepare \
  --output runs/calibration/expanded-localization-v1/human-review-copia
```

La preparació verifica els artefactes congelats, les deteccions i els PNG font.
Refusa sobreescriure una carpeta existent amb possibles decisions humanes.
