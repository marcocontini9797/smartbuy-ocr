"""Client of the Openapi "Catasto" API (catasto.openapi.it).

Configuration (.env):
    OPENAPI_CATASTO_TOKEN     bearer token created in console.openapi.com with the catasto scopes
    OPENAPI_CATASTO_SANDBOX   "true" (default) uses test.catasto.openapi.it: free, simulated answers
    OPENAPI_RICHIEDENTE_CF    tax code of the agent, sent as "richiedente" of mortgage inspections

POST requests are asynchronous in production: the client polls the request
until it is "evasa" or the wait expires; a request still running is returned
as pending with its id, and can be read later.
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

PRODUCTION_URL = "https://catasto.openapi.it"
SANDBOX_URL = "https://test.catasto.openapi.it"
DONE_STATES = {"evasa"}
FAILED_STATES = {"errore", "annullata", "rifiutata"}


class OpenapiError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class OpenapiPending(RuntimeError):
    """The request was accepted and is still being processed."""

    def __init__(self, request_id: str):
        super().__init__(f"request {request_id} still in progress")
        self.request_id = request_id


def configured() -> bool:
    return bool(os.getenv("OPENAPI_CATASTO_TOKEN", "").strip())


def environment() -> str:
    return "sandbox" if os.getenv("OPENAPI_CATASTO_SANDBOX", "true").strip().lower() != "false" else "production"


class CatastoClient:
    def __init__(self, token: str | None = None, sandbox: bool | None = None, http: httpx.Client | None = None,
                 wait_seconds: float = 45, poll_seconds: float = 3):
        token = (token or os.getenv("OPENAPI_CATASTO_TOKEN", "")).strip()
        if not token:
            raise OpenapiError("Servizio Catasto non configurato: manca OPENAPI_CATASTO_TOKEN")
        sandbox = environment() == "sandbox" if sandbox is None else sandbox
        self.environment = "sandbox" if sandbox else "production"
        self.http = http or httpx.Client(base_url=SANDBOX_URL if sandbox else PRODUCTION_URL, timeout=60,
                                         headers={"Authorization": f"Bearer {token}"})
        self.wait_seconds, self.poll_seconds = wait_seconds, poll_seconds

    # -- low level ---------------------------------------------------------
    def _json(self, method: str, path: str, **kwargs) -> Any:
        response = self.http.request(method, path, **kwargs)
        try:
            body = response.json()
        except ValueError as exc:
            raise OpenapiError(f"Risposta non valida da Openapi ({response.status_code})", response.status_code) from exc
        if response.status_code >= 400 or body.get("success") is False:
            message = body.get("message") or f"errore {response.status_code}"
            if response.status_code == 402:
                message = f"Credito Openapi insufficiente ({message})"
            raise OpenapiError(message, response.status_code)
        return body.get("data")

    def _wait(self, path: str, request_id: str) -> dict:
        deadline = time.monotonic() + self.wait_seconds
        while True:
            data = self._json("GET", f"{path}/{request_id}") or {}
            data = data.get("data", data)  # /richiesta/{id} wraps twice
            state = str(data.get("stato") or "").lower()
            if state in DONE_STATES:
                return data
            if state in FAILED_STATES or str(data.get("esito") or "").upper() in {"KO", "ERRORE"}:
                raise OpenapiError(f"Richiesta non evasa dal Catasto ({data.get('esito') or state})")
            if time.monotonic() >= deadline:
                raise OpenapiPending(request_id)
            time.sleep(self.poll_seconds)

    def _submit(self, post_path: str, get_path: str, body: dict) -> dict:
        data = self._json("POST", post_path, json=body) or {}
        if str(data.get("stato") or "").lower() in DONE_STATES:
            return data  # sandbox and some services answer synchronously
        request_id = data.get("id")
        if not request_id:
            raise OpenapiError("Openapi non ha restituito l'identificativo della richiesta")
        return self._wait(get_path, request_id)

    def resume(self, kind: str, request_id: str) -> dict:
        path = {"immobili": "/richiesta", "prospetto": "/richiesta", "visura_pdf": "/visura_catastale",
                "ispezione": "/ipotecarie"}[kind]
        return self._wait(path, request_id)

    # -- services ------------------------------------------------------------
    def search_address(self, provincia: str, comune: str, street: str) -> list[dict]:
        data = self._json("GET", "/indirizzo", params={"provincia": provincia, "comune": comune, "indirizzo": street})
        return (data or {}).get("indirizzi", []) if isinstance(data, dict) else []

    def units_at_address(self, id_indirizzo: str, civico: str | None) -> dict:
        body = {"id_indirizzo": id_indirizzo}
        if civico:
            body.update({"dal_civico": civico, "al_civico": civico})
        return self._submit("/richiesta/indirizzo", "/richiesta", body)

    def prospetto(self, *, provincia: str, comune: str, foglio: str, particella: str, subalterno: str | None,
                  sezione: str | None = None) -> dict:
        body = {"tipo_catasto": "F", "provincia": provincia, "comune": comune, "foglio": foglio, "particella": particella}
        if subalterno:
            body["subalterno"] = subalterno
        if sezione:
            body["sezione"] = sezione
        return self._submit("/richiesta/prospetto_catastale", "/richiesta", body)

    def visura_pdf(self, id_immobile: str) -> tuple[dict, bytes]:
        data = self._submit("/visura_catastale", "/visura_catastale",
                            {"entita": "immobile", "id_immobile": id_immobile, "tipo_visura": "ordinaria", "tipo_formato": "pdf"})
        return data, self.download_visura(data["id"])

    def download_visura(self, request_id: str) -> bytes:
        """PDF of a visura already bought (no new charge)."""
        response = self.http.get(f"/visura_catastale/{request_id}/documento")
        if response.status_code >= 400:
            raise OpenapiError("PDF della visura non ancora disponibile", response.status_code)
        return response.content

    def conservatoria_for(self, codice_catastale: str, hints: tuple[str, ...] = ()) -> str | None:
        """Name of the land registry office (conservatoria) covering a municipality.

        Offices are named after towns: those matching the hints (municipality,
        provincial capital) are checked first, so usually one or two lookups suffice.
        """
        offices = self._json("GET", "/territorio/conservatorie") or []
        wanted = [h.upper() for h in hints if h]
        offices.sort(key=lambda o: 0 if any(o.get("conservatoria", "").upper().startswith(h) for h in wanted) else 1)
        for office in offices:
            detail = self._json("GET", f"/territorio/conservatorie/{office['id']}") or {}
            blocks = detail if isinstance(detail, list) else [detail]
            for block in blocks:
                if any(c.get("codice_catastale") == codice_catastale for c in block.get("comuni") or []):
                    return block.get("conservatoria") or office["conservatoria"]
        return None

    def mortgage_notes(self, *, conservatoria: str, comune: str, foglio: str, particella: str, subalterno: str | None,
                       richiedente: str | None = None) -> dict:
        body: dict[str, Any] = {"entita": "ispezione_immobile", "conservatoria": conservatoria, "comune": comune,
                                "tipo_catasto": "F", "foglio": int(foglio), "particella": int(particella),
                                "motivo": "verifica preliminare per compravendita"}
        if subalterno:
            body["subalterno"] = int(subalterno)
        if richiedente or os.getenv("OPENAPI_RICHIEDENTE_CF"):
            body["richiedente"] = richiedente or os.getenv("OPENAPI_RICHIEDENTE_CF")
        return self._submit("/ipotecarie-elenco-note", "/ipotecarie", body)
