# SmartBuy Feedback Integration

## Stato

Il feedback è ora integrato nel document engine senza sostituire OCR, Fact,
Evidence, Issue o i repository esistenti. La persistenza usa `supabase-py` e
lo schema canonico `sb_properties`.

## Installazione

1. Eseguire `sql/002_feedback_intelligence.sql` nel Supabase SQL Editor.
2. Impostare nel backend `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` e
   `SMARTBUY_INTERNAL_TOKEN`.
3. Riavviare FastAPI.
4. Inviare feedback a `POST /api/v1/feedback` con header
   `X-SmartBuy-Internal-Token` e, per gli esperti,
   `X-SmartBuy-Actor-Role: DOMAIN_EXPERT`.

La service-role key deve restare nel backend. La migration abilita RLS e non
concede accesso diretto al browser.

## Versione del target

Prima di mostrare un oggetto correggibile, il backend deve fornire alla UI la
versione restituita dal repository: `updated_at` quando disponibile, altrimenti
un hash del payload canonico. La UI la rimanda come `expected_version`; un
feedback su un oggetto cambiato viene rifiutato con HTTP 409.

## Target attualmente collegati

- `FACT` → `property_facts`
- `EVIDENCE` → `fact_provenance`
- `DOCUMENT` → `documents`, con ownership verificata tramite `document_analyses`

`ISSUE`, `MISSING_INFO`, `RAG_*` e `RECOMMENDATION` vengono rifiutati finché il
contratto Fiverr non indica le rispettive tabelle canoniche. Questo impedisce
di fidarsi di ID inviati dal client o di creare duplicati.

## Ricalcolo

Ogni feedback accettato crea una riga idempotente in
`smartbuy_recalculation_jobs`. Un worker dovrà consumare gli stage in ordine e
marcare il job `completed` o `failed`. La correzione resta registrata e
auditabile anche quando il ricalcolo fallisce.

## Limiti ancora presenti nel repository

`api_server.py` e alcuni moduli del router importano componenti non presenti in
questa cartella (`red_flags`, `consistency`, `schemas`, `extraction`,
`fascicolo`, `llm_client`). Il feedback è testabile in isolamento, ma l'intera
API non può essere dichiarata avviabile finché questi moduli non vengono
recuperati o i relativi import vengono riallineati.
