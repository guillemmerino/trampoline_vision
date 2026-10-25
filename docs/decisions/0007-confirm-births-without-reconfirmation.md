# 0007. Confirmar naixements sense reconfirmar recuperacions

- Data: 24/10/2026.
- Estat: accepted; substitueix la política de confirmació de 0006, preservant la resta de fronteres.

## Context

El baseline real 0.3.0 i un reproduïdor sintètic mostren que OC-SORT 2.6.1 amb
minimum_consecutive_frames=3 pot assimilar mesures d'un track conegut i
retornar ID -1 fins a completar una nova ratxa. El nostre registre no pot
atribuir aquelles mesures i les mostra com a prediccions, amb semàntica incompleta.

## Decisió

Executar el backend amb mínim intern 1 i confirmar naixements al domini amb
`confirmation_policy=birth_streak_v1`. Un ID extern ha d'acumular
confirmation_frames associacions consecutives per convertir-se en identitat
pública. Un miss reinicia la ratxa pendent; les recuperacions de tracks ja
confirmats es publiquen a la primera mesura reassociada.

No es consulta estat privat, no es compta la detecció inicial -1 com si se
li conegués la identitat, no s'emeten esdeveniments per pendents que expiren i
no es reinterpreten observacions passades després de confirmar.

## Conseqüències

- Última observació, caixa mesurada i event recovered tornen a referenciar
  la mesura actual, sense retard artificial de reconfirmació.
- La nova política també s'aplica a l'inici del vídeo, evitant confirmar
  anticipadament per una excepció interna de bootstrap del backend.
- IDs i comptatges no són directament comparables amb 0.3.0; cal registrar
  versió, política i mínim intern efectius. El paquet puja a 0.4.0.
- Les proves cobreixen ratxa interrompuda, pendents expirats, naixements,
  recuperació immediata i la regressió real amb confirmació 3.
- La correcció no resol canvis entre persones ni qualitat de les mesures:
  són qüestions diferents i s'estudien amb experiments separats.

Evidència i resultats a la [guia 23](../23-confirmation-fix-and-improvement-study.md).
