# Estudi 02: confirmació 0.4.0 i tres variants

Vuit execucions del mateix cas: 0–3 s i 14–17 s per cadascuna de `fixed`,
`confidence005`, `dedup` i `partial`. L'última columna de la taula és l'únic
canvi respecte de la variant corregida.

| Prefix | Canvi respecte de 0.3.0 | Canvi experimental respecte de fixed |
| --- | --- | --- |
| `fixed` | Confirmació pròpia de naixements; backend amb mínim intern 1. | Cap. |
| `confidence005` | Mateixa correcció. | Confiança del tracker 0.05 en lloc de 0.1. |
| `dedup` | Mateixa correcció. | Deduplicació activada amb els llindars existents. |
| `partial` | Mateixa correcció. | `require_core=false`; es manté mínim de dos grups. |

Les configuracions a `configs/` són entrades executables d'experiment. Es
munten a `/experiments` i refereixen el manifest empaquetat, que accedeix a
TFM només per a lectura. No reutilitzar-les per altres casos sense resoldre
manifest, format i semàntica de coordenades.

Exemple des de l'arrel del projecte, amb una carpeta de sortida nova:

```powershell
docker compose --profile tracking run --rm --volume ./benchmarks/cases/JPN_AGE_1_000905_31.0/study-02/configs:/experiments:ro tracking track --config /experiments/confidence005-pipeline.json --start 14 --end 17 --output runs/confidence005-next-flight.json
```

`compare.py` només llegeix els artefactes existents i valida equivalència dels
registres de dedup/core, excloent run_id. Inclou els resultats 0.3.0 originals.
No compara els números d'identitat entre versions ni tracta més observacions
com una prova de millor identitat.

Les 22 àncores pilot són les mateixes de l'estudi 01, sense selecció posterior
segons el tracker. Són escasses, sense validació independent i amb una sola
proposta per persona/fotograma; l'alternativa correcta `45:81` continua sent
una limitació del comptatge sobre l'àncora `45:1`.

Resultats, interpretació i següents experiments al
[document 23](../../../../docs/23-confirmation-fix-and-improvement-study.md).
