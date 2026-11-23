# Simulació del camí del gimnasta

La simulació contrasta una decisió local amb un camí de cost mínim per
programació dinàmica. Totes dues estratègies parteixen de la mateixa caixa
inicial i fan servir els mateixos costos. El [pla executable](recovery-subject-path-simulation-v1.json)
fixa cinc escenes sintètiques construïdes per aïllar els problemes observats
al [catàleg de recovery](recovery-case-catalog-v1.md).

## Model

Cada fotograma aporta una llista de candidates amb ID, centre i escala.
Totes les candidates entren al graf. Cada estat recorda les dues
últimes observacions. L’aresta següent valora el desplaçament per
fotograma, el canvi de velocitat, la mida i el canvi d’ID, amb un cost per
cada fotograma sense observació. Es permeten salts d’un màxim de cinc
fotogrames intermedis, i el camí es pot acabar deixant el tram restant
sense observació. Els costos i el límit de salt són paràmetres sintètics
del pla.

La decisió local tria a cada fotograma l’opció immediata de menor cost,
amb el buit com a alternativa. El camí global minimitza la suma de costos
fins al final del clip. Als fotogrames d’interès es calcula el millor
camí sota cada possible elecció, inclosa l’absència d’observació. Amb
un marge de 0,08 o menys, el cas queda pendent com a ambigüitat. Les etiquetes
de quines caixes localitzen el gimnasta es fan servir després per avaluar
el resultat i distingir un empat d’identitat d’un empat entre dues
caixes útils.

## Resultats

| Escena | Decisió local | Camí global |
| --- | --- | --- |
| Buit als fotogrames 4 i 5 | A la reaparició entra a la caixa equivocada, que encara porta l’ID 92. | Salta del 3 al 6, deixa dos buits i reprèn el gimnasta amb l’ID 44. El cost global és 2,766 si tria el 44 i 3,273 si tria el 92 al 6. |
| Transferència al fotograma 3 | Manté l’ID 29 quan passa a un altre actor. | Tria el 114 al fotograma del canvi. El cost global és 1,235 pel 114 i 1,615 si es força el 29. |
| Reaparició ambigua | Tria una de les dues caixes simètriques. | Els dos camins costen 1,747. Els fotogrames 4 i 5 queden marcats com a ambigus. |
| Dues caixes útils | Tria una caixa. | Les dues opcions empaten. La referència sintètica confirma que totes dues localitzen el gimnasta. |
| Distractor amb moviment més regular | Segueix el distractor durant tres fotogrames. | Fa el mateix, amb marge de cost suficient per donar la decisió per resolta. |

El primer cas mostra com les observacions posteriors permeten rebutjar
una reaparició que semblava millor localment. El darrer mostra el límit
de la geometria: una trajectòria equivocada pot satisfer millor el model
de moviment. El marge només reflecteix la preferència d’aquest model.

## Reproducció

Des de l’arrel del repositori, amb Python 3.10 o superior i un directori
de sortida nou.

```bash
python3 -m benchmarks.calibration.tools.simulate_recovery_subject_path \
  --plan benchmarks/calibration/config/studies/recovery-subject-path-simulation-v1.json \
  --output runs/calibration/recovery-subject-path-simulation-v1-repeat
```

L’informe verificat és a
`runs/calibration/recovery-subject-path-simulation-v1-verified/summary.json`.
Desa la configuració, les empremtes del pla i el codi, els camins triats,
els costos de cada aresta, els fotogrames saltats i les alternatives.
S’han comprovat 34 mínims amb enumeració exhaustiva dels camins de les
cinc escenes, incloses les alternatives forçades. Les xifres corresponen
a escenes artificials i pesos triats per mostrar comportaments.
La [prova posterior sobre els vídeos reals](recovery-subject-path-v1.md)
contrasta el mateix cost geomètric amb les traces congelades.
