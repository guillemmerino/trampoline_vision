# Benchmarks

El benchmark esportiu formal és posterior. Inicialment es definiran casos tècnics de seguiment
i límits de salts, amb anotacions petites i protocol reproduïble.

Registrar versió, conjunt de dades, configuració, recursos i mètriques. Vegeu
[validació](../docs/12-validation-strategy.md). Encara no hi ha benchmark formal.

La primera revisió real de tracking té anotacions pilot i un reproduïdor de
reconfirmació a [cases/JPN_AGE_1_000905_31.0](cases/JPN_AGE_1_000905_31.0/README.md).
Són evidències de fallades i diagnòstics dispersos, amb limitacions explícites;
no són mètriques exhaustives ni una comparació validada d'algoritmes.

`cases/JPN_AGE_1_000905_31.0/study-03` conserva l'exploració de geometria i
associació feble, amb prototips ByteTrack fora del paquet de producció.
Diagnòstic i límits al [document 24](../docs/24-final-geometry-and-weak-evidence-diagnosis.md).

`cases/JPN_AGE_1_000905_31.0/study-04` reprodueix les caixes YOLO independents
del clip complet amb set controls OC-SORT/ByteTrack. Inclou scripts,
configuracions, resultats i notes d'una mostra local revisada. La cobertura
millora, però la continuïtat global continua fallant; veure el
[document 25](../docs/25-independent-box-tracking-study.md).
