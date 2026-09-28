# Openapi Catasto Sandbox test

SmartBuy already has a Catasto client in `integrations/openapi_catasto.py`; this smoke test reuses it and never targets production. Sandbox answers are simulated, so they test the integration flow but are not real cadastral evidence.

The backend `.env` uses these names:

```env
OPENAPI_CATASTO_SANDBOX_TOKEN=your-openapi-sandbox-token
OPENAPI_CATASTO_SANDBOX=true
OPENAPI_CATASTO_TOKEN=your-production-token
OPENAPI_RICHIEDENTE_CF=
```

Keep both tokens private in `.env`; it is gitignored. Sandbox and production credentials are selected separately, so you do not need to overwrite the production token to test. The richiedente CF can remain empty for a Prospetto Catastale test. It is only optionally sent by the current client with a mortgage inspection request.

Run offline client/parser tests (mocked HTTP; no external requests):

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider test_registry.py -q
```

Run one Sandbox request after the local token is configured:

```powershell
.\.venv\Scripts\python.exe scripts\openapi_sandbox_smoke.py
```

The smoke test reports status and field counts only; it never prints names or tax codes. It uses example identifiers from Openapi's public documentation and explicitly constructs `CatastoClient(sandbox=True)`.
