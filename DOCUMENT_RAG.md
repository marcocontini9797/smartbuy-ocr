# RAG sul testo dei documenti

Prima l'agente rispondeva solo da fatti estratti e citazioni di provenienza: il testo dei documenti non era ricercabile.
Ora ogni documento caricato viene indicizzato e l'agente recupera i brani pertinenti.

## Flusso
1. **Upload** (`api/document_routes.py`): il testo OCR viene diviso in chunk (`rag_chunking.py`: ~900 caratteri, per pagina e
   intestazione, con sovrapposizione), arricchito da una riga di contesto deterministica ("Tipo «file» — pag. N — sezione — unità"),
   embeddato (`text-embedding-3-large`, 1536 dim) e salvato in `document_chunks` (`rag_index.py`, idempotente per hash).
2. **Domanda** (`rag_service.retrieve_passages`): ricerca ibrida nell'RPC `smartbuy_search_chunks` (semantica pgvector +
   full-text italiano), fusione RRF pesata, riformulazione delle domande brevi, **rerank LLM** (modello leggero) e
   **soglia di rilevanza**: se nessun brano risponde, `strength = none` e il prompt dice di non inventare.
3. **Risposta** (`agent_llm_gateway.py`): i brani entrano come `brani_di_documenti` accanto alle evidenze; le citazioni
   `(fonte: file, pag. N)` (anche `pagg. N-M`) diventano le fonti mostrate.

Sicurezza: tabella con RLS (`private.owns_property`), RPC `security invoker`, documenti sostituiti (`superseded_by`) esclusi.
Tutto fallisce in modo morbido: senza chiave OpenAI o migrazione, l'agente torna ai soli fatti.

## Misure (`evaluation/evaluate_rag.py`, giudice = frase d'oro nel testo recuperato)
- Senza LLM il solo algoritmo migliora poco rispetto al prototipo; i pesi contano poco.
- Il **rerank LLM** è il salto grande, e la soglia di rilevanza separa nettamente: domande con risposta ≥ 0,95,
  domande senza risposta ≤ 0,60 su tutti e tre i corpus. Soglie in produzione: forte 0,85, debole 0,65.
- Corpus sintetico: va riconfermato su documenti reali prima di fidarsi dei numeri assoluti.

Comandi: `python -m evaluation.evaluate_rag --live --llm --corpus scale`.

## Ciclo di feedback
Ogni risposta registra una **traccia** (`agent_retrieval_traces`: chunk usati, rilevanza, embedding della domanda); 👍/👎 nella chat
(`agent_answer_feedback.trace_id`) la valutano. Il feedback agisce in due modi:
1. **Subito, nello stesso fascicolo** (`rag_search.apply_hints`, RPC `smartbuy_feedback_hints`): una domanda simile (coseno ≥ 0,88)
   a una già valutata fa salire i chunk validati con 👍 (anche se non erano tra i candidati) e scendere quelli bocciati con 👎.
   Non rimuove mai un chunk: il fascicolo potrebbe aver ricevuto nel frattempo il documento giusto.
2. **Nel tempo, su tutto il sistema** (`rag_calibration.py`, `GET /ops/rag/calibration`, workflow n8n `rag-calibrazione.json`):
   confronta la rilevanza dei brani delle risposte utili e di quelle segnalate e propone la soglia debole. Solo con almeno 15
   valutazioni per gruppo; la soglia la applica una persona.
Verifica dal vivo: `scripts/smoke_rag_feedback.py` (inserimento, ricerca, traccia, suggerimenti, nessuna ereditarietà da domande diverse).
Limite onesto: la ripetizione di domande simili nello stesso fascicolo è rara; il valore principale è la calibrazione.

## Auto-miglioramento robusto (`rag_learning.py`, ogni notte via n8n `rag-apprendimento.json`)
Principio: **il feedback umano è un indizio, non una verità**. Cosa può cambiare da solo è poco e limitato; il resto resta umano.

1. **Verifica delle valutazioni** (`rag_trust.py`): un giudice LLM legge i brani veri e dice se la risposta è supportata. Umano e giudice
   d'accordo → etichetta accettata; in disaccordo → "in revisione", non usata. Peso per utente = storico di accordo col giudice
   (partenza neutra 0,5); utenti che il giudice contraddice sono silenziati; sconti per raffiche, voti sempre uguali, auto-contraddizioni.
   Un 👎 insegna alla soglia solo se anche il giudice trova la risposta non supportata (altrimenti non è un problema di ricerca).
2. **Cosa si impara** (`rag_tuner.py`): solo il filtro di rilevanza (`weak_relevance`, `weak_similarity`), perché si può rigiocare
   esattamente dalle tracce (`candidates`) senza richiamare modelli. Limiti rigidi (`rag_config.BOUNDS`) e un solo passo piccolo per ciclo.
3. **Protezioni prima di adottare**: almeno 40 etichette, 10 per classe, 3 utenti diversi; nessun utente oltre il 20% del peso;
   le risposte utili restano ≥95%; il guadagno deve reggere togliendo qualsiasi singolo utente e avere limite inferiore bootstrap > 0.
4. **Rollback automatico**: se con la nuova configurazione la quota di 👍 accettati scende di oltre 10 punti rispetto alla precedente
   (≥20 valutazioni per parte) si torna alla versione prima. Dopo un cambio, 7 giorni di pausa.
5. **Tracciabilità**: `rag_configs` (versioni con motivo e numeri), `rag_feedback_labels` (verdetto su ogni valutazione).
Verifica dal vivo: `scripts/smoke_rag_learning.py` (ripristina tutto). Non impara: pesi di fusione, chunking, prompt (servono ancora
`evaluation/` e una persona). Limite: con pochi agenti il ciclo resterà "dati insufficienti" per un po'; è voluto.

### Segnale implicito (meno dipendenza dai pulsanti)
Ogni traccia conserva la risposta data. Se lo stesso utente, nello stesso fascicolo, rifà entro 3 minuti una domanda molto simile
(coseno ≥ 0,85), la risposta precedente è sospetta; il giudice la verifica e solo se la trova non supportata diventa un'etichetta
negativa di peso basso (0,3). Non serve nessun clic dell'agente. Verifica dal vivo: `scripts/smoke_rag_reask.py`.
