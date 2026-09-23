from datetime import date

import pytest

from document_engine.cross_validation import (
    codice_fiscale_valid, cross_validate, norm_address, norm_categoria, norm_catasto_id,
    norm_energy_class, norm_people, parse_date, parse_number, parse_quota, summarize,
)

TODAY = date(2026, 9, 23)


def fact(name, value, doc=None, conf=0.95, source_type="document", fid=None):
    return {"id": fid or f"{name}-{doc}-{value}", "fact_name": name, "fact_value": {"value": value},
            "source_document_id": doc, "source_type": source_type, "confidence_score": conf}


def by_field(findings):
    return {f.field: f for f in findings}


# --- normalizers -----------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("320.000", 320000.0), ("€ 320.000,00", 320000.0), ("1.234,56", 1234.56), ("1,234.56", 1234.56),
    ("92 mq", 92.0), ("92,5 m²", 92.5), ("1.5", 1.5), (74, 74.0), ("n/d", None),
])
def test_parse_number_handles_italian_formats(raw, expected):
    assert parse_number(raw) == expected


@pytest.mark.parametrize("raw", ["14/09/2026", "14-09-2026", "2026-09-14", "14 settembre 2026", "14.09.26"])
def test_parse_date_formats(raw):
    assert parse_date(raw) == date(2026, 9, 14)


def test_catasto_ids_ignore_labels_and_leading_zeros():
    assert norm_catasto_id("Fg. 0285") == norm_catasto_id("285") == norm_catasto_id("foglio 285") == "285"
    assert norm_catasto_id("mapp. 1234") == "1234"
    assert norm_catasto_id("sub 12") == "12"


@pytest.mark.parametrize("raw", ["A/2", "A2", "a/02", "cat. A-2", "Categoria A/2 classe 3"])
def test_categoria_normalization(raw):
    assert norm_categoria(raw) == "A/2"


@pytest.mark.parametrize("raw,expected", [("B", "B"), ("Classe energetica: A2", "A2"), ("a4", "A4"), ("A+", "A+"), ("classe G", "G")])
def test_energy_class_normalization(raw, expected):
    assert norm_energy_class(raw) == expected


def test_people_are_order_and_title_insensitive():
    assert norm_people(["ROSSI Giovanni"]) == norm_people(["Sig. Giovanni Rossi"])
    assert norm_people("Rossi Giovanni nato a Bologna il 01/01/1960") == norm_people(["Giovanni Rossi"])


def test_address_expands_abbreviations():
    assert norm_address("V. Vizzani n. 72") == norm_address("Via Vizzani, 72") == ("via vizzani", "72")


@pytest.mark.parametrize("raw,expected", [("proprietà esclusiva", 1.0), ("Proprieta' per 1/2", 0.5), ("piena proprietà", 1.0), ("boh", None)])
def test_quota_parsing(raw, expected):
    assert parse_quota(raw) == expected


def test_codice_fiscale_checksum():
    assert codice_fiscale_valid("RSSMRA80A01H501U")
    assert not codice_fiscale_valid("RSSMRA80A01H501X")
    assert not codice_fiscale_valid("not a cf")


# --- cross-validation ----------------------------------------------------------

def test_same_value_written_differently_across_documents_is_consistent():
    findings = by_field(cross_validate(1, facts=[
        fact("riferimento", {"foglio": "Fg. 0285", "particella": "mapp. 1234", "subalterno": "sub 12", "categoria": "A2"}, doc=1),
        fact("riferimenti_catastali", [{"foglio": "285", "particella": "1234", "subalterno": "12", "categoria": "A/2"}], doc=2),
    ], today=TODAY))
    for key in ("catasto.foglio", "catasto.particella", "catasto.subalterno", "catasto.categoria"):
        assert findings[key].status == "consistent", key
        assert findings[key].confidence > 0.95


def test_different_subalterno_is_a_high_severity_conflict():
    findings = by_field(cross_validate(1, facts=[
        fact("riferimento", {"foglio": "285", "subalterno": "12"}, doc=1),
        fact("riferimento", {"foglio": "285", "subalterno": "13"}, doc=2),
    ], today=TODAY))
    assert findings["catasto.subalterno"].status == "conflict"
    assert findings["catasto.subalterno"].severity == "high"
    assert findings["catasto.foglio"].status == "consistent"


def test_repeated_extractions_of_one_document_are_not_independent_confirmations():
    findings = by_field(cross_validate(1, facts=[fact("epgl", 74, doc=2, fid=f"e{i}") for i in range(4)], today=TODAY))
    assert findings["epgl"].status == "insufficient_evidence"


def test_divergent_extractions_of_one_document_are_extraction_unstable_not_conflict():
    # Real case from property 16: one APE read as "B" four times and "A2" twice.
    facts = [fact("energy_class", "B", doc=2, conf=0.98, fid=f"b{i}") for i in range(4)]
    facts += [fact("energy_class", "A2", doc=2, conf=0.98, fid=f"a{i}") for i in range(2)]
    findings = cross_validate(16, facts=facts, today=TODAY)
    statuses = {f.status for f in findings if f.field == "classe_energetica"}
    assert statuses == {"extraction_unstable"}
    unstable = next(f for f in findings if f.field == "classe_energetica")
    assert unstable.canonical_value == "B"
    assert unstable.confidence < 0.98


def test_owner_names_match_across_visura_and_atto():
    findings = by_field(cross_validate(1, documents=[
        {"id": 1, "document_type": "visura_catastale", "extracted_fields": {"intestatari": ["ROSSI Giovanni", "BIANCHI Anna"]}},
        {"id": 2, "document_type": "atto_compravendita", "extracted_fields": {
            "parte_venditrice": ["Anna Bianchi", "Sig. Giovanni Rossi"], "parte_acquirente": ["Luca Verdi"]}},
    ], today=TODAY))
    assert findings["proprietari"].status == "consistent"


def test_seller_not_on_visura_is_a_conflict():
    findings = by_field(cross_validate(1, documents=[
        {"id": 1, "extracted_fields": {"intestatari": ["Rossi Giovanni"]}},
        {"id": 2, "extracted_fields": {"parte_venditrice": ["Rossi Giovanni", "Rossi Maria"]}},
    ], today=TODAY))
    assert findings["proprietari"].status == "conflict"
    assert "Maria" in findings["proprietari"].detail


def test_surface_within_tolerance_is_compatible_and_utile_vs_commerciale_uses_ratio():
    findings = by_field(cross_validate(1, facts=[
        fact("superficie_dichiarata_mq", "92 mq", doc=1),
        fact("surface_m2", 93, doc=2),
        fact("superficie_utile_mq", "78,5", doc=3),
    ], today=TODAY))
    assert findings["superficie_commerciale_mq"].status == "compatible"
    assert findings["superficie.rapporto"].status == "compatible"


def test_implausible_utile_vs_commerciale_ratio_is_flagged():
    findings = by_field(cross_validate(1, facts=[
        fact("superficie_dichiarata_mq", 92, doc=1), fact("superficie_utile_mq", 40, doc=2),
    ], today=TODAY))
    assert findings["superficie.rapporto"].status == "conflict"


def test_price_mismatch_between_preliminare_and_atto():
    findings = by_field(cross_validate(1, documents=[
        {"id": 1, "extracted_fields": {"prezzo_eur": {"valore": "€ 320.000,00", "confidence": 0.9}}},
        {"id": 2, "extracted_fields": {"prezzo_eur": {"valore": "310.000", "confidence": 0.9}}},
    ], today=TODAY))
    assert findings["prezzo_eur"].status == "conflict"
    assert findings["prezzo_eur"].severity == "high"


def test_invalid_codice_fiscale_and_expired_ape_and_stale_visura():
    findings = by_field(cross_validate(1, documents=[
        {"id": 1, "extracted_fields": {"intestatari": ["Rossi Mario RSSMRA80A01H501X"], "data_visura": "01/03/2026"}},
        {"id": 2, "extracted_fields": {"data_emissione": "10/01/2015", "data_scadenza": "10/01/2025"}},
    ], today=TODAY))
    assert findings["codice_fiscale"].status == "invalid"
    assert findings["ape.scadenza"].status == "invalid"
    assert findings["visura.data"].status == "attention"


def test_valid_codice_fiscale_is_not_flagged():
    findings = cross_validate(1, documents=[{"id": 1, "extracted_fields": {"intestatari": ["Rossi Mario RSSMRA80A01H501U"]}}], today=TODAY)
    assert not any(f.field == "codice_fiscale" for f in findings)


def test_findings_are_ordered_by_urgency_and_summary_counts_blocking():
    findings = cross_validate(1, facts=[
        fact("epgl", 74, doc=1),
        fact("riferimento", {"foglio": "1"}, doc=1), fact("riferimento", {"foglio": "2"}, doc=2),
    ], today=TODAY)
    assert findings[0].status == "conflict"
    summary = summarize(findings)
    assert summary["conflicts"] == 1 and summary["blocking"] == 1


def test_finding_ids_are_stable():
    facts = [fact("energy_class", "C", doc=1), fact("energy_class", "C", doc=2)]
    assert [f.finding_id for f in cross_validate(1, facts=facts)] == [f.finding_id for f in cross_validate(1, facts=facts)]


def test_property_sheet_address_is_checked_against_documents():
    # Real case from property 16: sheet says Via Vizzani 72, the visura says Via Giustiniano 456.
    findings = by_field(cross_validate(16, facts=[
        fact("riferimento", {"comune": "Bologna", "indirizzo": "Via Giustiniano, 456"}, doc=2),
    ], property_record={"address": "Via Vizzani 72", "city": "Bologna"}, today=TODAY))
    assert findings["indirizzo"].status == "conflict"
    assert findings["catasto.comune"].status == "consistent"


def test_property_sheet_alone_produces_no_single_source_noise():
    findings = cross_validate(1, property_record={"address": "Via Vizzani 72", "city": "Bologna", "surface_m2": 92}, today=TODAY)
    assert findings == []
