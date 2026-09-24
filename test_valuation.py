from document_engine.valuation import build_valuation, calibration_from_outcomes

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


BOLOGNA_SHOP_YIELD = {"scope": "comune", "label": "BOLOGNA", "n": 41, "p25": 0.0544, "p50": 0.0593, "p75": 0.0667}


def test_commercial_capitalises_zone_rent_at_the_municipal_market_yield():
    result = build_valuation(property_record={"property_type": "commerciale", "surface_m2": 60, "condition": "Buono",
                                              "asking_price": 200000}, zone=ZONE, yield_stats=BOLOGNA_SHOP_YIELD)
    names = [m["name"] for m in result["methods"]]
    assert names == ["Comparativo (quotazioni OMI negozi)", "Reddituale (capitalizzazione diretta del canone)"]
    income = result["methods"][1]
    assert income["low"] == round(7.5 * 60 * 12 / 0.0667, -3)
    assert income["high"] == round(11.5 * 60 * 12 / 0.0544, -3)
    assert income["mid"] == round(9.5 * 60 * 12 / 0.0593, -3)
    assert result["yield"]["zone_implied"] == round(9.5 * 12 / 2175, 4)
    assert result["asking_price"]["position"] in {"below", "within", "above"}


def test_without_yield_statistics_the_fallback_is_declared():
    result = build_valuation(property_record={"property_type": "commerciale", "surface_m2": 60}, zone=ZONE)
    assert any("valore nazionale di riserva" in c for c in result["caveats"])


def test_commercial_uses_actual_lease_rent_when_available():
    result = build_valuation(property_record={"property_type": "commerciale", "surface_m2": 60}, zone=ZONE,
                             facts=[{"fact_name": "canone_mensile_eur", "fact_value": {"value": "1.200"}}], yield_stats=BOLOGNA_SHOP_YIELD)
    income = result["methods"][1]
    assert "canone del contratto in essere 1.200" in income["explanation"]
    assert income["mid"] == round(14400 / 0.0593, -3)
    comparative = result["methods"][0]
    assert result["range"]["mid"] == round(0.4 * comparative["mid"] + 0.6 * income["mid"], -3)


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



def test_cadastral_category_selects_the_omi_typology():
    zone = {**ZONE, "quotes": ZONE["quotes"] + [
        {"comune": "BOLOGNA", "cod_tip": "21", "tipologia": "Abitazioni di tipo economico", "stato": "NORMALE", "compr_min": 2000, "compr_max": 2500}]}
    facts = [{"fact_name": "riferimento", "fact_value": {"value": {"categoria": "A/3", "foglio": "1"}}}]
    result = build_valuation(property_record={"surface_m2": 100}, zone=zone, facts=facts)
    assert "tipo economico" in result["methods"][0]["name"]
    assert result["range"]["low"] == 200000


def test_garage_in_the_documents_is_added_with_omi_box_values():
    zone = {**ZONE, "quotes": ZONE["quotes"] + [
        {"comune": "BOLOGNA", "cod_tip": "13", "tipologia": "Box", "stato": "NORMALE", "compr_min": 1500, "compr_max": 2350}]}
    facts = [{"fact_name": "riferimenti_catastali", "fact_value": {"value": [
        {"categoria": "A/2", "subalterno": "5"}, {"categoria": "C/6", "consistenza": "15 m²", "subalterno": "12"}]}}]
    result = build_valuation(property_record={"surface_m2": 75, "condition": "Buono"}, zone=zone, facts=facts)
    assert result["additions"][0]["low"] == 22000
    assert result["range"]["low"] == 225000  # 75 m² x 2.700 + 15 m² x 1.500


def test_residential_reports_market_rent_and_yield_at_asking_price():
    result = build_valuation(property_record={"surface_m2": 75, "condition": "Buono", "asking_price": 245000}, zone=ZONE)
    assert result["market_rent"]["mid"] == round(11.5 * 75, -1)
    assert result["asking_price"]["gross_yield"] == round(round(11.5 * 75, -1) * 12 / 245000, 4)


def test_confidence_lists_missing_inputs():
    result = build_valuation(property_record={"surface_m2": 75}, zone=ZONE)
    assert result["confidence"]["level"] == "bassa"
    assert "categoria catastale da visura" in result["confidence"]["missing"]


NORTH_EAST_ZONE = {**ZONE, "area_territoriale": "NORD-EST"}
BASE = {"property_type": "residenziale", "surface_m2": 100, "condition": "Buono"}


def test_listings_are_discounted_by_the_macro_area_negotiation_discount():
    comps = [{"kind": "annuncio", "price": 400000, "surface_m2": 100}] * 3
    result = build_valuation(property_record=BASE, zone=NORTH_EAST_ZONE, comparables=comps)
    method = result["methods"][-1]
    assert method["mid"] == 380000  # 4.000 €/m² less 5% (North-East)
    assert "5%" in method["explanation"]
    # OMI mid 285.000 blended with 30% weight for three comparables
    assert result["range"]["mid"] == round((0.7 * 285000 + 0.3 * 380000) / 1000) * 1000


def test_sold_comparables_are_not_discounted_and_unknown_area_uses_national_discount():
    comps = [{"kind": "venduto", "price": 300000, "surface_m2": 100}, {"kind": "annuncio", "price": 300000, "surface_m2": 100},
             {"kind": "venduto", "price": 300000, "surface_m2": 100}]
    method = build_valuation(property_record=BASE, zone=ZONE, comparables=comps)["methods"][-1]
    assert method["low"] == 279000 and method["high"] == 300000  # listing less 7%


def test_fewer_than_three_comparables_are_not_used():
    result = build_valuation(property_record=BASE, zone=ZONE, comparables=[{"kind": "venduto", "price": 1, "surface_m2": 1}])
    assert len(result["methods"]) == 1
    assert any("almeno 3" in c for c in result["caveats"])


def test_calibration_needs_five_sales_and_uses_the_median_ratio():
    outcomes = [{"sale_price": 90, "estimate_mid": 100, "comune": "Bologna"}] * 4
    few = calibration_from_outcomes(outcomes, "BOLOGNA")
    assert few == {"n": 4, "scope": "tutte le vendite", "applied": False, "factor": 0.9, "mean_abs_error": 0.1}
    many = calibration_from_outcomes(outcomes + [{"sale_price": 95, "estimate_mid": 100, "comune": "Bologna"}], "Bologna")
    assert many["applied"] and many["scope"] == "comune" and many["factor"] == 0.9


def test_applied_calibration_scales_the_range_and_keeps_the_uncalibrated_estimate():
    calibration = {"n": 6, "scope": "comune", "applied": True, "factor": 0.9}
    result = build_valuation(property_record=BASE, zone=ZONE, calibration=calibration)
    assert result["range"]["uncalibrated"]["mid"] == 285000
    assert result["range"]["mid"] == 256000
    assert result["adjustments"][-1]["pct"] == -0.1
