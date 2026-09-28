# SmartBuy — cross-validation v3

Questa versione estende il motore esistente. I risultati confluiscono negli
endpoint di cross-validation, checklist e nelle azioni suggerite all’agente.
Nessuna nuova tabella, chiamata a pagamento o migrazione del database.

## Controlli aggiunti

| Area | Comportamento |
| --- | --- |
| Soggetti | Venditore storico, acquirente, promittente venditore e locatore restano ruoli distinti. Il confronto con la visura richiede la stessa unità identificata; per un acquisto servono anche date coerenti. |
| Quote | Somme separate per diritto e unità; proprietà e usufrutto non si sommano. Duplicati esclusi, letture diverse evidenziate. Un elenco parziale non viene presunto completo. |
| Formalità | Stato attivo, cancellazione richiesta e cancellazione parziale richiedono approfondimento. Stati diversi si collegano solo tramite identificativo e unità. Nessuna cancellazione o assenza di gravami viene certificata dal motore. |
| Locazione | Registrazione esplicitamente negativa, termine trascorso e disponibilità dichiarata in presenza di un contratto generano verifiche. La scadenza non equivale alla riconsegna. |
| Trattativa | Condizioni prive di esito, dettaglio incompleto, date illeggibili e termini trascorsi restano visibili. Nessuna decadenza del contratto è dedotta automaticamente. |
| Condominio | Limitazioni, morosità menzionata e quota superiore al totale della delibera. Una morosità generica non viene attribuita al venditore. |
| Tecnica | Difformità elencate anche in presenza di una sintesi positiva, titoli con stato non concluso, dichiarazioni impianti negative. |
| Importi | Prezzi richiesti, concordati o relativi a periodi diversi vanno riconciliati prima di parlare di contraddizione. |
| Feedback | Correzioni con nomi alternativi dello stesso campo rispettate anche nei confronti per unità; provenienza conservata nel percorso API. |
| Seconda lettura | Confronto dei ruoli e dei nuovi record strutturati; ordine delle righe e formattazione della citazione non diventano incongruenze. |

Restano attivi i controlli v2 su categorie/uso, C/2, pertinenze, date,
superfici, identificativi, fonti duplicate, documenti simulati ed errori di lettura.
I vecchi test che equiparavano il venditore storico all’intestatario attuale sono
stati corretti: una concordanza di nominativi non prova titolarità o poteri di firma.

## Cosa riceve l’interfaccia

`GET /api/v1/properties/{id}/cross-validation` conserva i campi precedenti e restituisce:

- `summary.engine_version = "3.0"`.
- `findings`: identificativo stabile, regola/versione, ambito, fonti, percorsi dei campi,
  citazioni/pagine quando disponibili, prove e azione suggerita.
- `agent_review.actions`: attività raggruppate con referente, priorità e collegamento alle segnalazioni.
- `agent_review.coverage`: dieci aree operative; dati mancanti, disponibili da esaminare,
  confrontati in parte o da approfondire. Nessuna percentuale di completezza giuridica.
- `agent_review.questions`: richieste concrete per completare gli input mancanti.

Le nuove segnalazioni usano il percorso già esistente di checklist/azioni.
La mappa `coverage` e le domande `questions` sono disponibili nell’API: questa
iterazione non introduce un nuovo pannello nel frontend.

## File principali

- `document_engine/transaction_validation.py`: controlli contestuali di ruoli, quote e condizioni operative.
- `document_engine/validation_coverage.py`: mappa degli input e dei confronti disponibili.
- `document_engine/cross_validation.py`: integrazione, distinzione dei ruoli e seconda lettura.
- `document_engine/validation_rules.py`: correzioni canoniche, provenienza e ammissibilità delle fonti.
- `schemas.py`: strutture opzionali per titolarità, formalità, condizioni e termine di locazione.
- `document_engine/agent_review.py`, `checklist.py`, `api/operations_routes.py`: collegamenti applicativi.
- `test_validation_engine_v3.py`: casi sintetici e percorso API con correzione umana e provenienza.

## Compatibilità e limiti

I nuovi campi sono opzionali e usano `extracted_fields`, già esistente. I documenti
analizzati in precedenza non acquistano automaticamente dati mancanti: per popolare
i nuovi dettagli serve una nuova analisi o una correzione supportata dalla fonte.
In questa iterazione non sono state lanciate analisi LLM né spese API.

Il motore segnala incoerenze e verifiche operative. Non ricostruisce automaticamente
ogni successione, procura, regime patrimoniale, sanatoria o vicenda giudiziaria;
non interpreta geometricamente le planimetrie; non risolve da solo formalità o
condizioni contrattuali tra operazioni non identificate. La mancanza di una
segnalazione non è un via libera alla vendita o all’uso dell’immobile.

Le fonti vengono confrontate solo entro gli ambiti supportati; documenti con più
unità e parti globali non attribuite richiedono collegamento esplicito. Le regole
giuridiche preesistenti del progetto non sono state sottoposte a revisione normativa
in questa iterazione. L’accuratezza OCR richiede una valutazione separata su documenti
reali con risposte di riferimento validate da professionisti.

## Verifica riproducibile

Eseguire dalla cartella `smartbuy-ocr`:

```powershell
.\.venv\Scripts\python.exe -B scripts\test_engine_offline.py --tb=short
```

Il runner blocca le connessioni esterne e disabilita i test live. Il report JUnit
è generato in `evaluation/reports/validation-offline.xml` (ignorato da Git).
Il risultato misura regressioni sui casi inclusi, non sensibilità su tutti i rischi immobiliari.

Le modifiche sono locali; per usarle il backend deve ricaricare il codice.
Server in esecuzione, login e database reale non sono stati verificati con questi test.

Verifica del 28 settembre 2026: **382 test superati**, 73 casi aggiunti rispetto ai 309 della v2. Nove avvisi di deprecazione preesistenti nelle librerie e nel codice (uno compare anche nel nuovo test API); nessun test fallito. Nessuna connessione esterna o chiamata a pagamento.
