# Identità dei documenti e versioni del fascicolo

Livello sopra `document_similarity.compare_documents`. Il confronto dice *quanto* due
documenti si somigliano; questo livello dice *che cosa significa* la differenza. Tutto è
deterministico, senza chiamate a provider AI e senza costi. Niente viene mai unito,
sostituito o cancellato in automatico (`automatic_merge_allowed` è sempre `false`).

## Percorso di un caricamento

1. `POST /api/v1/properties/{id}/documents` analizza il file e lo salva (come prima).
2. Il testo OCR viene richiesto a `ingest_document` (`include_ocr_text=True`, mai restituito
   al browser) e salvato in `document_text_extractions` (RLS: solo il proprietario).
3. `_fascicolo_review` confronta il nuovo documento con quelli già in pratica, esclusi i
   falliti e le versioni sostituite. Il testo OCR salvato si usa solo per i documenti dello
   stesso tipo. Un errore qui non fa fallire il caricamento: il campo vale `null`.
4. La risposta contiene `fascicolo`: `compared_with`, `needs_review` e un elemento per
   documento confrontato (`action`, `reason`, `identity_verdict`, `lineage`,
   `open_conflicts`, `existing_file_name`).

## Adapter (`document_identity.adapt_extracted_fields`)

Mappa i campi di estrazione nel formato letto dal motore, solo per il confronto:
`riferimento` -> `riferimenti_catastali`, `data_visura`/`data_rilascio`/... -> `document_date`
(ISO, oppure `gg/mm/aaaa` letta giorno-prima). Date discordanti o illeggibili non vengono
scelte. Il nome del comune perde "Comune di" e la sigla finale ("BOLOGNA (BO)" = "Bologna").
Non inventa mai un `document_series_id` e non modifica i dati salvati.

## Verdetti del resolver (`resolve_document_identity`)

| Verdetto | Significato |
| --- | --- |
| `newer_version_candidate` | stessa unità e tipo, data di emissione diversa; `lineage` = `explicit_series` o `inferred_from_unit_type_and_date` |
| `same_unit_different_document_types` | stessa unità, tipo diverso (visura + planimetria): normale |
| `same_unit_conflict` | stessa unità e data, dati che non coincidono |
| `unit_outside_expected` | unità diversa da quelle attestate dalle visure della pratica |
| `ancillary_unit_candidate` | categoria da pertinenza (C/2, C/6, C/7): da confermare |
| `neither_matches_expected`, `overlapping_units_review`, `different_units_expectation_unknown` | unità da verificare |
| `identity_unresolved` | mancano gli estremi catastali |
| `exact_duplicate`, `out_of_scope`, `likely_same_document`, `same_unit_unresolved` | come da similarity |

I numeri OCR che cambiano solo perché cambia la data di emissione sono "spiegati"
(`explained`); un numero cambiato che non è una data resta tra gli `open_conflicts`.
L'unità attesa è quella delle visure catastali già in pratica (`properties` non ha colonne
catastali). Un nome di comune contro un codice catastale non si equipara: resta `unknown`.

## Azioni del Fascicolo Builder

`new_version` / `older_version` (con `previous_document_id`), `review_conflict`, `review_unit`,
`add_document`, più quelle già esistenti. Una unità catastale diversa non finisce più in
`add_document` senza revisione.

## Sostituire una versione

`documents.superseded_by` (+ `superseded_at`). Non cancella nulla: riga, file e fatti restano.

- `POST /properties/{id}/documents/{old}/supersede` con `{"replaced_by": new}`: solo tra
  documenti della stessa pratica, dello stesso tipo, il nuovo completato e a sua volta non
  sostituito (422/409/404 altrimenti).
- `DELETE` sullo stesso percorso ripristina il documento.
- Le versioni sostituite escono da cross-validation, checklist, valutazione, intelligence,
  risposte dell'agente, fascicolo condiviso e dall'unità attesa (`document_engine/superseded.py`).
  Restano nell'elenco documenti con "Ripristina".

## Migrazioni

`20261002154717_document_text_owner_access` (policy e permessi su
`document_text_extractions`, che prima non erano raggiungibili dall'utente) e
`20261002154725_document_superseded_by`.

## Limiti noti

- I suggerimenti compaiono al momento del caricamento; non c'è ancora un riepilogo
  persistente per i documenti già in pratica, né la memoria di un "tieni entrambi".
- Variazioni catastali documentate: lo schema di estrazione non ha campi per i riferimenti
  prima/dopo, quindi non sono riconosciute.
- Per i documenti caricati prima di questa funzione non c'è testo OCR salvato: il confronto
  usa solo i campi estratti.
