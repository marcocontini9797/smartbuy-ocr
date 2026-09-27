# SmartBuy OCR API

This repository contains the document analysis API used by `smartbuy-web`.
Run `main_api:app` for the complete property workspace. `api_server:app` is the
legacy OCR-only application and does not expose the property workspace routes.

## Local start

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements_api.txt
.\.venv\Scripts\python.exe -m uvicorn main_api:app --host 127.0.0.1 --port 8000
```

Configure `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and `OPENAI_API_KEY` as described
in `.env.example`. The workspace routes use the caller's Supabase access token;
they do not need a service-role key. OCR requires an OpenAI API key and available
credit when a document is uploaded.

The `smartbuy/` package is the local copy of the existing profile, document
facts loader, validation, and risk implementation. It was moved here from the
surrounding `smartbuy-casa-diretta/smartbuy/` checkout so this repository can
start by itself. It does not add a second database schema. Keep these modules
together when updating the profile and risk rules.

Uploads accept PDF, PNG, and JPEG up to 20,000,000 bytes. The frontend applies
the same limit. Run `.\.venv\Scripts\python.exe -m pytest -q` before release.
