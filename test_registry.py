import httpx
import pytest

from document_engine import registry
from integrations.openapi_catasto import CatastoClient, OpenapiError, OpenapiPending


def test_split_address_keeps_street_and_house_number():
    assert registry.split_address("Via Zamboni 33") == ("ZAMBONI", "33")
    assert registry.split_address("via dell'Indipendenza, 12/A") == ("DELL'INDIPENDENZA", "12")
    assert registry.split_address("Piazza Maggiore") == ("MAGGIORE", None)


def test_pick_address_prefers_the_exact_street():
    candidates = [{"id_indirizzo": "a", "indirizzo": "VIA ZAMBONI VECCHIA"}, {"id_indirizzo": "b", "indirizzo": "VIA ZAMBONI"}]
    assert registry.pick_address(candidates, "ZAMBONI")["id_indirizzo"] == "b"
    assert registry.pick_address([], "ZAMBONI") is None


PROSPETTO = {"id": "r1", "stato": "evasa", "risultato": {"immobili": [{
    "foglio": 200, "particella": 105, "subalterno": 12, "indirizzo": "VIA ZAMBONI n. 33 Piano 2", "categoria": "A/2",
    "classe": "3", "consistenza": "5,5 vani", "rendita": "Euro:1.022,58", "id_immobile": "imm-1",
    "intestatari": [{"denominazione": "ROSSI MARIO", "cf": "RSSMRA80A01A944X", "proprieta": "Proprieta'", "quota": "1/2"},
                    {"denominazione": "BIANCHI ANNA", "cf": "BNCNNA82B41A944Y", "proprieta": "Proprieta'", "quota": "1/2"}]}]}}


def test_prospetto_becomes_visura_fields_with_owners_and_rent():
    fields, owners = registry.visura_fields(PROSPETTO, "Bologna")
    assert fields["intestatari"] == ["ROSSI MARIO", "BIANCHI ANNA"]
    assert fields["codici_fiscali_intestatari"][0] == "RSSMRA80A01A944X"
    assert fields["riferimento"]["foglio"] == "200" and fields["riferimento"]["subalterno"] == "12"
    assert fields["riferimento"]["rendita_catastale_eur"] == 1022.58 and owners[1]["quota"] == "1/2"
    assert registry.visura_fields({"risultato": {"immobili": []}}, "Bologna") == (None, [])


def notes(*rows):
    return {"risultato": {"risultato": {"immobili": [{"note": [
        {"tipo_nota": kind, "data_nota": when, "tipo_atto": act} for kind, when, act in rows]}]}}}


def test_seizure_in_the_notes_is_severe_and_feeds_the_red_flags():
    summary = registry.mortgage_summary(notes(("TRASCRIZIONE A FAVORE", "10/03/2015", "COMPRAVENDITA"),
                                              ("ISCRIZIONE CONTRO", "10/03/2015", "IPOTECA VOLONTARIA"),
                                              ("TRASCRIZIONE CONTRO", "02/05/2025", "VERBALE DI PIGNORAMENTO IMMOBILI")))
    assert summary["severe"] and summary["last_transfer"]["tipo_atto"] == "COMPRAVENDITA"
    fields = registry.mortgage_fields(summary, {"comune": "Bologna"})
    assert "PIGNORAMENTO" in fields["tipo_formalita"] and fields["formalita_ancora_attiva"] is None


def test_clean_inspection_is_explicitly_without_formalities():
    summary = registry.mortgage_summary(notes(("TRASCRIZIONE A FAVORE", "10/03/2015", "COMPRAVENDITA")))
    assert not summary["prejudicial"] and "Nessuna" in summary["reading"]
    assert registry.mortgage_fields(summary, {})["formalita_ancora_attiva"] is False


def fake(handler):
    return CatastoClient(token="t", http=httpx.Client(base_url="https://test", transport=httpx.MockTransport(handler)),
                         wait_seconds=0.05, poll_seconds=0.01)


def test_client_polls_an_asynchronous_request_until_done():
    calls = []

    def handler(request: httpx.Request):
        calls.append((request.method, request.url.path))
        if request.method == "POST":
            return httpx.Response(200, json={"success": True, "data": {"id": "r1", "stato": "in_erogazione"}})
        done = len(calls) > 2
        return httpx.Response(200, json={"success": True, "data": {"data": {**PROSPETTO, "stato": "evasa" if done else "in_erogazione"}}})

    result = fake(handler).prospetto(provincia="BO", comune="BOLOGNA", foglio="200", particella="105", subalterno="12")
    assert result["risultato"]["immobili"][0]["id_immobile"] == "imm-1"
    assert calls[0] == ("POST", "/richiesta/prospetto_catastale")


def test_client_reports_pending_and_credit_errors():
    def slow(request):
        if request.method == "POST":
            return httpx.Response(200, json={"success": True, "data": {"id": "r9", "stato": "in_erogazione"}})
        return httpx.Response(200, json={"success": True, "data": {"data": {"id": "r9", "stato": "in_erogazione"}}})

    with pytest.raises(OpenapiPending) as pending:
        fake(slow).prospetto(provincia="BO", comune="BOLOGNA", foglio="1", particella="2", subalterno=None)
    assert pending.value.request_id == "r9"

    def broke(request):
        return httpx.Response(402, json={"success": False, "message": "Insufficient Credit in Wallet: 0.10", "error": 246})

    with pytest.raises(OpenapiError, match="Credito Openapi insufficiente"):
        fake(broke).search_address("BO", "BOLOGNA", "ZAMBONI")
