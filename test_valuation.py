from document_engine.valuation import build_valuation

# Real OMI 2025/2 quotations of Bologna zone C4 (Via Zamboni).
ZONE = {"zona": "C4", "fascia": "C", "descrizione": None, "semestre": "2025/2", "quotes": [
    {"comune": "BOLOGNA", "cod_tip": "20", "tipologia": "Abitazioni civili", "stato": "OTTIMO", "compr_min": 2900, "compr_max": 4200, "loc_min": None, "loc_max": None},
    {"comune": "BOLOGNA", "cod_tip": "20", "tipologia": "Abitazioni civili", "stato": "NORMALE", "compr_min": 2700, "compr_max": 3000, "loc_min": 9.5, "loc_max": 13.5},
    {"comune": "BOLOGNA", "cod_tip": "5", "tipologia": "Negozi", "stato": "OTTIMO", "compr_min": 2450, "compr_max": 3200, "loc_min": 9, "loc_max": 12.5},
    {"comune": "BOLOGNA", "cod_tip": "5", "tipologia": "Negozi", "stato": "NORMALE", "compr_min": 1900, "compr_max": 2450, "loc_min": 7.5, "loc_max": 11.5},
]}


def test_residential_normal_state_is_omi_range_times_surface():
    result = build_valuation(property_record={"property_type": "residenziale", "surface_m2": 75, "condition": "Buono"}, zone=ZONE)
    assert result["status"] == "ok"
    assert result["range"]["low"] == 202000 and result["range"]["high"] == 225000


def test_residential_adjustments_for_energy_and_floor():
    result = build_valuation(property_record={"property_type": "residenziale", "surface_m2": 100, "condition": "Buono",
                                              "floor": 3, "elevator": False},
                             zone=ZONE, facts=[{"fact_name": "classe_energetica", "fact_value": {"value": "G"}}])
    labels = {a["label"]: a["pct"] for a in result["adjustments"]}
    assert labels == {"Classe energetica G": -0.06, "Piano 3 senza ascensore": -0.08}
    assert result["range"]["low"] == round(270000 * 0.86, -3)


def test_renovated_uses_ottimo_quotation():
    result = build_valuation(property_record={"property_type": "residenziale", "surface_m2": 100, "condition": "Ristrutturato"}, zone=ZONE)
    assert result["range"]["low"] == 290000 and result["range"]["high"] == 420000


def test_commercial_combines_comparative_and_income():
    result = build_valuation(property_record={"property_type": "commerciale", "surface_m2": 60, "condition": "Buono",
                                              "asking_price": 200000}, zone=ZONE)
    names = [m["name"] for m in result["methods"]]
    assert names == ["Comparativo (quotazioni OMI negozi)", "Reddituale (capitalizzazione del canone)"]
    income = result["methods"][1]
    assert income["low"] == round(7.5 * 60 * 12 / 0.08, -3) and income["high"] == round(11.5 * 60 * 12 / 0.06, -3)
    assert result["asking_price"]["position"] in {"below", "within", "above"}


def test_commercial_uses_actual_lease_rent_when_available():
    result = build_valuation(property_record={"property_type": "commerciale", "surface_m2": 60}, zone=ZONE,
                             facts=[{"fact_name": "canone_mensile_eur", "fact_value": {"value": "1.200"}}])
    assert "canone del contratto 1.200" in result["methods"][1]["explanation"]


def test_missing_surface_or_zone_is_explained():
    assert "superficie" in build_valuation(property_record={"property_type": "residenziale"}, zone=ZONE)["reason"]
    assert "Zona OMI" in build_valuation(property_record={"surface_m2": 80}, zone=None)["reason"]


def test_surface_from_documents_when_sheet_has_none():
    result = build_valuation(property_record={"property_type": "residenziale"}, zone=ZONE,
                             facts=[{"fact_name": "superficie_catastale_mq", "fact_value": {"value": 110}}])
    assert result["surface"]["source"] == "visura (superficie catastale)"


def test_zone_in_another_municipality_is_refused():
    other = {**ZONE, "quotes": [{**q, "comune": "GRANAROLO DELL`EMILIA"} for q in ZONE["quotes"]]}
    result = build_valuation(property_record={"city": "Bologna", "surface_m2": 60}, zone=other)
    assert result["status"] == "unavailable" and "Granarolo" in result["reason"]


def test_same_municipality_accepts_province_suffix():
    assert build_valuation(property_record={"city": "Bologna (BO)", "surface_m2": 60}, zone=ZONE)["status"] == "ok"


def test_divergent_methods_are_flagged():
    prime = {**ZONE, "quotes": [{"comune": "BOLOGNA", "cod_tip": "5", "tipologia": "Negozi", "stato": "NORMALE",
                                 "compr_min": 1850, "compr_max": 3200, "loc_min": 16.5, "loc_max": 29}]}
    result = build_valuation(property_record={"property_type": "commerciale", "surface_m2": 60}, zone=prime)
    assert any("divergono" in c for c in result["caveats"])
