# OCR and document analysis v2

The account upload uses `document_engine/document_reader.py` through `api_server.py`.
It reads every PDF page, retains explicit page boundaries, renders at most
OCR_CONCURRENCY pages at once (hard cap 4), and reuses one HTTP client.
The previous account-upload path read only page 1.

A PDF above OCR_MAX_PAGES is rejected before rendering or AI calls. A failed,
empty, refused or truncated OCR response stops analysis; it cannot become a
completed document. OCR confidence is null because it has not been calibrated.
The returned OCR metadata contains page text, page number, model and version,
and is saved in the existing run-stage metadata when observability is available.

Classification sees the complete transcription. Extraction and verification
run off the async event loop. An extraction/verification failure returns an
error instead of success with empty fields. A failed optional second reading
caps overall confidence at 0.5 and is recorded separately. Unsupported nested
fields receive a confidence penalty, as do unsupported plain persisted facts.

Configuration is documented in .env.example. The frontend waits up to ten
minutes; processing remains synchronous and exceptionally long documents may
exceed that. Background jobs/resumable page checkpoints are not implemented.

Validation: offline provider mocks cover all-page reading, ordering, limits,
page failure, truncated responses, auth failure, nested verification, ingestion
failure and persistence confidence. A three-page in-memory PDF also exercises
real Poppler rendering. These tests establish pipeline behavior, not measured
OCR accuracy on real property documents. No live paid model benchmark was run.
Existing uploaded documents are not automatically reanalysed.
