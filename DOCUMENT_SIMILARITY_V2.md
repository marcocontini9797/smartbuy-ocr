# SmartBuy Document Similarity v2

File completo: document_engine/document_similarity.py.
Richiede solo la libreria standard Python. Nessuna API, nessun costo per confronto.
Le quattro funzioni pubbliche della v1 restano disponibili.

## Uso

```python
from document_engine.document_similarity import compare_documents
result = compare_documents(document_a, document_b)
print(result["status"])
print(result["conflicts"])
```

Dati riconosciuti:
- sha256, content_sha256, checksum_sha256, file_sha256: SHA-256 valido;
- document_type, ocr_text;
- metadata ed extracted_fields (anche wrapper valore/value);
- riferimenti_catastali: Comune/codice Comune, sezione, foglio, particella, subalterno, categoria;
- property_id/fascicolo_id, user_id/agente_id e tenant_id, se forniti;
- document_series_id esplicito, document_date/issue_date/data_emissione ISO;
- environment/source_mode, anche in metadata, per separare simulazioni e dati reali.

## Risultati

- duplicate: SHA-256 dichiarati validi e coincidenti; punteggio 1.
- similar: contenuto OCR sufficientemente ricco e simile; non prova identità.
- same_document_updated: candidato aggiornamento, con serie esplicita, stesso tipo,
  unità catastali identiche e data di emissione successiva non futura.
  Leggere sempre version.assessment e version.newer.
- possible_conflict: differenze strutturate o numeriche da verificare.
- different: elementi comparabili differenti.
- insufficient_evidence: pochi dati o limiti superati; non implica documenti diversi.
- out_of_scope: account/pratiche/ambienti incompatibili nei dati ricevuti.

automatic_merge_allowed è sempre false: nessuna cancellazione/sostituzione automatica.
requires_review guida la revisione; il punteggio è una misura euristica di somiglianza,
NON una probabilità calibrata o un giudizio di validità legale.

## Correzioni rispetto alla v1

- Senza hash coincidente la v1 arrivava al massimo a 0,60: similar a soglia 0,65
  era irraggiungibile. La v2 distingue hash e somiglianza del contenuto.
- Tipi assenti non sono una corrispondenza.
- Campi vuoti e metadati tecnici non sono prove di similarità.
- La copertura dei metadati considera l'unione dei campi.
- Il confronto testo è simmetrico e limitato, con token e sequenze di caratteri.
- Normalizza maiuscole, spazi e sillabazioni a fine riga.
- Segnala variazioni di numeri anche in moduli con molto testo uguale.
- Confronta le categorie per unità, senza confondere appartamento e garage.
- Non deduce revisioni dalla data di upload o da metadati generici simili.
- Distinzioni economiche: superficie utile e commerciale non vengono mescolate.
- Confidenza, citazioni e ordine dei campi non alterano l'identità del dato.
- Non modifica gli input e non restituisce valori identificativi nei motivi.

## Limiti e integrazione

Hash in input sono dichiarati dal chiamante: calcolarli dai byte con
calculate_file_hash quando si riceve il file. Il confronto non apre PDF né esegue OCR.
Un hash diverso può comunque appartenere a una scansione dello stesso documento.

Il chiamante deve applicare autenticazione/RLS e fornire documenti della pratica:
il modulo confronta gli ID ricevuti, non autorizza accessi al database.

Il confronto numerico riconosce alcuni formati italiani/internazionali e rifiuta
interpretazioni ambigue. Non sostituisce la cross validation giuridica o tecnica.
Le soglie richiedono calibrazione su casi reali revisionati.

I limiti sono 200.000 caratteri OCR per documento, 4.000 elementi strutturati,
200.000 caratteri strutturati complessivi per normalizzazione e 200 unità catastali.
Al superamento non confronta soltanto il prefisso, ma segnala dati non sufficienti.

Il confronto è chiamato dal caricamento documenti (`POST /properties/{id}/documents`,
tramite `fascicolo_integration.build_fascicolo_comparisons`) in modo solo consultivo:
vedi DOCUMENT_IDENTITY.md per come vengono interpretate le differenze e per la
sostituzione di una versione. I consumer devono gestire tutti gli stati, compresi quelli nuovi.

## Test

63 test dedicati; 500 test offline dell'intero checkout superati.
Nessuna richiesta a provider AI, Supabase o servizi a pagamento.
Comando: .venv/Scripts/python.exe -B scripts/test_engine_offline.py --tb=short
