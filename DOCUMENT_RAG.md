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
