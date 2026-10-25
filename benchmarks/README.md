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

L'[estudi 05](studies/05-reid/README.md) compara OC-SORT amb BoT-SORT sense
ReID i amb OSNet preentrenat sobre tres clips complets. Inclou un protocol
fixat, anotacions de pilot versionades, Docker CPU, resultats i reutilització
verificada de descriptors per refinar associació sense repetir inferència.
La millora parcial i els límits són al
[document 26](../docs/26-reid-tracking-comparison.md).


L'[estudi 06](studies/06-configurable-tracking/README.md) comprova la integració
0.5.0: backends configurables, CSV independent, descriptors externs i cache.
Les nou traces del pilot 05 es reprodueixen exactament, amb proves del paquet
instal·lat i d’inferència real. És una regressió d’integració; la coherència
de l’actor i el matching d’esquelets continuen pendents.

El [banc de calibratge del servidor](calibration/README.md) prepara un corpus
portable de 94 vídeos (pilot de 18), pesos locals verificats i bateries
detector/tracking amb represa i monitorització. Les referències independents
i la validació GPU són passos explícits; no es declaren defaults òptims a
partir dels recomptes operatius.
