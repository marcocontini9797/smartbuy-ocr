"""Run one fake-data Prospetto Catastale request on the existing client, sandbox only."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from integrations.openapi_catasto import CatastoClient, OpenapiError, configured  # noqa: E402


def main() -> int:
    if not configured():
        print("Configura OPENAPI_CATASTO_SANDBOX_TOKEN nel .env del backend (mai inviarlo in chat).", file=sys.stderr)
        return 2
    if os.getenv("OPENAPI_CATASTO_SANDBOX", "true").strip().lower() == "false":
        print("Test interrotto: OPENAPI_CATASTO_SANDBOX è false; non chiamo la produzione.", file=sys.stderr)
        return 2

    client = CatastoClient(sandbox=True)
    try:
        print("Invio una richiesta Prospetto Catastale al solo host Sandbox...")
        data = client.prospetto(
            provincia="RM", comune="ROMA", foglio="872", particella="405", subalterno="48"
        )
        units = ((data.get("risultato") or {}).get("immobili") or [])
        owners = [owner for unit in units for owner in (unit.get("intestatari") or [])]
        summary = {
            "environment": client.environment,
            "status": data.get("stato"),
            "result": data.get("esito"),
            "request_id": data.get("id"),
            "units_count": len(units),
            "unit_fields": sorted(units[0].keys()) if units else [],
            "owners_count": len(owners),
            "owners_with_cf_count": sum(bool(owner.get("cf")) for owner in owners),
            "notice": "Sandbox response is simulated; it is not cadastral evidence.",
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except OpenapiError as exc:
        print(f"Test Sandbox non completato: {exc}", file=sys.stderr)
        return 1
    finally:
        client.http.close()


if __name__ == "__main__":
    raise SystemExit(main())
