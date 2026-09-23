from evaluation.evaluate_extraction import compare


def test_compare_uses_domain_normalization():
    rows = {r["field"]: r for r in compare(
        {"riferimento": {"foglio": "285", "categoria": "A/2"}, "intestatari": ["Rossi Giovanni"], "data_visura": "14/09/2026"},
        {"riferimento": {"foglio": "Fg. 0285", "categoria": "A3"}, "intestatari": ["Giovanni ROSSI"], "data_visura": "2026-09-14"},
    )}
    assert rows["catasto.foglio"]["correct"] and rows["proprietari"]["correct"] and rows["data_visura"]["correct"]
    assert not rows["catasto.categoria"]["correct"]


def test_missing_field_is_wrong():
    assert compare({"classe_energetica": "C"}, {})[0]["note"] == "mancante"
