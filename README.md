# SmartBuy OCR API

This repository contains the FastAPI backend used by `smartbuy-web`.
Run `main_api:app` for the complete property workspace. `api_server:app` is
the legacy OCR-only application and does not expose the property workspace routes.

## Local start

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements_api.txt
.\.venv\Scripts\python.exe -m uvicorn main_api:app --host 127.0.0.1 --port 8000
```

## Required configuration

Set the variables described in `.env.example`.

For Supabase, prefer the current key model:

- `SUPABASE_PUBLISHABLE_KEY` (`sb_publishable_...`) for user-scoped and anonymous clients.
- `SUPABASE_SECRET_KEY` (`sb_secret_...`) only for backend-only privileged flows.
- `SUPABASE_ANON_KEY` and `SUPABASE_SERVICE_ROLE_KEY` remain temporary fallbacks during migration.

The normal property workspace never uses the privileged key: it validates the
caller's Supabase access token and performs database/storage operations as that
user, so RLS remains authoritative.

A privileged backend key is nevertheless required by the complete
`main_api:app` today because specific server-only features intentionally need
it, including seller-lead persistence and signing an already-authorized shared
document path. Never copy the secret/service-role key into `smartbuy-web` or a
browser-visible environment variable.

OCR requires `OPENAI_API_KEY` and available API credit when a document is uploaded.

The `smartbuy/` package is the local copy of the existing profile, document
facts loader, validation, and risk implementation. It was moved here from the
surrounding `smartbuy-casa-diretta/smartbuy/` checkout so this repository can
start by itself. It does not add a second database schema.

Uploads accept PDF, PNG, and JPEG up to 20,000,000 bytes. The frontend applies
the same application-level limit.

Supabase's canonical migration ledger lives in `supabase/migrations/`.
The legacy `sql/` directory is retained for historical/bootstrap reference.

Run the test suite before release:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```
