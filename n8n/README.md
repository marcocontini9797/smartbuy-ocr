# Workflow n8n

## rag-manutenzione.json
Ogni notte alle 3: legge lo stato dell'indice RAG (`GET /ops/rag/health`); se ci sono documenti con testo
ma senza chunk, li indicizza (`POST /ops/rag/backfill`, 50 per volta); se dopo il tentativo l'arretrato
resta, manda una mail.

Configurazione:
1. Backend: imposta `SMARTBUY_OPS_SECRET` (stringa lunga casuale) e riavvia. Senza, gli endpoint `/ops/*` sono disattivati (503).
2. n8n: variabili d'ambiente `SMARTBUY_API_URL` (es. `https://api...`) e `SMARTBUY_OPS_SECRET` (lo stesso valore).
   Se n8n blocca `$env` (`N8N_BLOCK_ENV_ACCESS_IN_NODE`), sostituisci le due espressioni con credenziali "Header Auth".
3. Importa il file (Workflows → Import from file), imposta le credenziali SMTP sul nodo "Avvisa" e cambia il destinatario.
4. Prova con "Execute workflow" prima di attivarlo.

Gli endpoint restituiscono solo conteggi, nessun contenuto dei documenti.

## rag-calibrazione.json
Ogni lunedì alle 8 manda un rapporto sulla calibrazione della ricerca (`GET /ops/rag/calibration`): quante risposte
sono state valutate, quanto erano rilevanti i brani trovati per quelle utili e per quelle no, e (con almeno 15 valutazioni
per gruppo) quale soglia di rilevanza terrebbe le risposte utili rifiutando quelle segnalate. Contiene solo numeri.
Le soglie non si applicano da sole: le cambia una persona in `document_engine/rag_search.py` dopo aver confrontato
la proposta con `evaluation/`.

## rag-apprendimento.json
Ogni notte alle 4 lancia il ciclo di apprendimento (`POST /ops/rag/learn`) e avvisa con una mail solo se la RAG ha
adottato una nuova configurazione o è tornata alla precedente. Il ciclo verifica le valutazioni degli agenti
(giudice + affidabilità dell'utente), propone nuove soglie e le adotta solo se tutte le protezioni reggono; vedi
`DOCUMENT_RAG.md`. `GET /ops/rag/config` mostra lo storico con i motivi e i numeri di ogni cambio.
Il workflow `rag-calibrazione.json` resta come rapporto settimanale di sola lettura.
