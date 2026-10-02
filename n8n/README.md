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

## feedback-settimanale.json
Ogni lunedì alle 8: legge le risposte dell'agente che gli utenti hanno segnato 👎 negli ultimi 7 giorni
(`GET /ops/feedback/negative`) e, se ce ne sono, manda una mail con domanda, risposta, fonti e commento.
Servono le stesse variabili e lo stesso segreto del workflow precedente. Ogni segnalazione è un candidato
caso di test: le domande dove l'agente ha sbagliato con le fonti giuste mostrano un problema di
risposta, quelle senza fonti un problema di ricerca (da aggiungere a `evaluation/rag_corpus*.py`).
Il riepilogo contiene testo di domande e risposte: usa un destinatario interno.
