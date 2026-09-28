# SmartBuy — percorso di verifica dell’agente (motore 3.1)

## Obiettivo

Passare dall’elenco di differenze a un percorso di approfondimento: quale unità,
quale operazione, quali prove, quali spiegazioni possibili e quale verifica viene
prima. Il motore rimane deterministico e usa i dati estratti dalla pipeline esistente.
Questa versione non addestra un nuovo LLM e non esegue chiamate a pagamento.

## Nuovi comportamenti

1. **Preliminare e definitivo:** confronto di venditori, acquirenti e prezzo solo
   con richiamo esplicito alla stessa operazione, data coerente, oggetto completo
   e documenti indicati come sottoscritti. Una stessa casa può avere molte compravendite.
2. **Oggetto:** confronto dell’intero insieme di unità, comprese le pertinenze.
   Una pertinenza esclusa o identificativi diversi richiedono approfondimento
   prima di confrontare il prezzo complessivo.
3. **Esito delle condizioni:** citazioni affidabili su una stessa clausola possono
   essere proposte come prova da esaminare. Identificativi ambigui, fonti derivate
   o esiti discordanti non diventano una prova conclusiva. La chiusura non è automatica.
4. **Percorso di verifica:** ogni caso espone osservazioni, fonti, ipotesi esplicitamente
   non confermate, verifiche discriminanti, referente e prove richieste per chiuderlo.
5. **Dipendenze:** una lettura incerta precede i confronti che usano quella fonte.
   Una fonte incerta non blocca automaticamente verifiche indipendenti su altre fonti.
6. **Copertura per unità:** i dati di due subalterni non vengono sommati per completare
   un singolo fascicolo. I valori globali di documenti con più unità restano da attribuire.
7. **Cronologia:** date, unità e richiami delle fonti sono disponibili in una sequenza
   consultabile, applicando prima le correzioni dell’agente. L’operazione corrente
   non viene scelta automaticamente quando il collegamento manca o è ambiguo.

## Integrazione

L’endpoint esistente `/api/v1/properties/{id}/cross-validation` continua a restituire
`findings`, `summary` e `agent_review`. Le aggiunte sono:

- `summary.engine_version = "3.1"`.
- `agent_review.investigation_plan`, versione `1.0`:
  `cases`, `timeline`, `context_questions`, `next_case_id`.
- Ogni caso: `case_id`, `finding_ids`, `scope`, `sources`, `evidence_ids`,
  `observations`, `possible_explanations`, `closure_requirements`, `blocked_by`,
  `assigned_role`, `next_step`, `automatic_closure = false`.
- `agent_review.coverage.domains[].units` e `unassigned_sources`:
  fonti e input mancanti separati per unità.

I nuovi confronti confluiscono anche nel percorso esistente di checklist e azioni.
Il piano dettagliato è pronto nell’API; in questa iterazione non è stato costruito
un nuovo pannello frontend. Nessuna tabella o migrazione è stata aggiunta.

### Dati di estrazione opzionali

`schemas.py` aggiunge `collegamento_operazione` a preliminare e atto:
`riferimento`, `data` dell’operazione richiamata, `stato_documento`, `fonte`,
`confidence`. L’atto può riportare `condizioni_dettaglio`, senza presumere che una
condizione si sia avverata per la sola esistenza del definitivo.

I documenti già elaborati non acquisiscono questi dati automaticamente. Le nuove
verifiche si attivano quando sono presenti dati supportati da fonti, ottenuti tramite
nuova analisi o correzione. I confronti già disponibili restano operativi.

## Verifica e significato del voto

Un voto architetturale è una valutazione qualitativa, non una misura di accuratezza.
Il progetto dispone di un esempio dimostrativo per l’estrazione, non di un corpus
di fascicoli reali validati che consenta di attribuire un voto complessivo affidabile.

Per misurare la qualità sul campo occorrono fascicoli rappresentativi di vendita
e affitto, residenziali e commerciali, con esiti di riferimento controllati da
professionisti. Misurare separatamente:

- errori OCR ed estrazione dei singoli campi;
- criticità attese trovate e criticità mancate;
- falsi allarmi e punti presentati prematuramente come chiariti;
- correttezza di unità, ruolo, operazione e cronologia;
- utilità delle prove richieste e tempo necessario all’agente per arrivarci;
- regressioni dopo modifiche di prompt, modelli o regole.

Le soglie di confidenza usate dalle regole sono precauzioni implementative da
calibrare sul corpus; non rappresentano probabilità di correttezza dimostrate.
Il numero di test superati non misura quanti rischi del mondo reale siano coperti.

## Riproduzione locale

```powershell
.\.venv\Scripts\python.exe -B scripts\test_engine_offline.py --tb=short
```

Il runner esclude i test live e blocca le connessioni esterne. Il report è in
`evaluation/reports/validation-offline.xml`. I nuovi casi sono in
`test_agent_reasoning_v31.py`, compreso il percorso API con correzioni e provenienza.

Modifiche locali: richiedono ricaricamento del backend. Non è stato eseguito il push
né verificato un server remoto. Le regole normative preesistenti non sono state
oggetto di revisione giuridica in questa iterazione.

Verifica finale: **424 test superati**, 42 nuovi casi rispetto ai 382 della versione precedente. Dieci avvisi di deprecazione nel codice/librerie esistenti, nessun errore. Nessuna chiamata esterna o a pagamento.
