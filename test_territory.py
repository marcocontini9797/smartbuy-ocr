from document_engine.hazards import flood_level, landslide_level
from document_engine.territory import build_territory, ipab_area, price_update
from document_engine.valuation import build_valuation
from test_valuation import ZONE

# Real ISPRA GetFeatureInfo answers (text/plain), trimmed.
FLOOD_P1_P2 = """Results for FeatureType 'https://idrogeo.isprambiente.it:pericolosita_idraulica_p1':
--------------------------------------------
id = 27176
scenariop1 = Aree a pericolosita' idraulica bassa P1
--------------------------------------------
Results for FeatureType 'https://idrogeo.isprambiente.it:pericolosita_idraulica_p2':
--------------------------------------------
id = 29493
scenariop2 = Aree a pericolosita' idraulica media P2
--------------------------------------------"""
LANDSLIDE_P4 = """Results for FeatureType 'https://idrogeo.isprambiente.it:pericolosita_frane':
--------------------------------------------
id = 957786
cod_per_it = 4
--------------------------------------------"""


def test_ispra_answers_give_the_highest_class_at_the_point():
    assert flood_level(FLOOD_P1_P2) == 2
    assert flood_level("no features were found") == 0
    assert landslide_level(LANDSLIDE_P4) == 4
    assert landslide_level("cod_per_it = AA\n") == 5
    assert landslide_level("cod_per_it = AA\ncod_per_it = 2\n") == 2  # a real class outranks an attention area


def test_flood_hazard_at_the_point_raises_an_alert_and_questions():
    point = {"flood_level": 3, "flood_label": "elevata (P3, tempo di ritorno 20–50 anni)", "landslide_level": 0,
             "landslide_label": "nessuna"}
    result = build_territory(seismic={"zona": "3"}, municipal_hazard=None, point=point, incomes=[], postcode=None)
    assert result["alerts"][0]["level"] == "high" and "P3" in result["alerts"][0]["text"]
    assert any("allagamenti" in q for q in result["questions"])
    assert result["seismic"]["high"] is False


def test_seismic_zone_2_asks_about_structure():
    result = build_territory(seismic={"zona": "2B"}, municipal_hazard=None, point=None, incomes=[], postcode=None)
    assert result["seismic"]["high"] and "sottozona 2B" in result["seismic"]["reading"]
    assert any("Sismabonus" in q for q in result["questions"])


def test_incomes_compare_postcode_with_municipality_and_2019():
    incomes = [{"anno": 2019, "cap": "", "reddito_imponibile_medio_eur": 26744},
               {"anno": 2024, "cap": "", "reddito_imponibile_medio_eur": 31449, "contribuenti": 310489},
               {"anno": 2024, "cap": "40136", "reddito_imponibile_medio_eur": 58398}]
    result = build_territory(seismic=None, municipal_hazard=None, point=None, incomes=incomes, postcode="40136")["incomes"]
    assert result["municipal_mean"] == 31449 and result["change_since_2019"] == 0.176
    assert result["postcode_mean"] == 58398 and result["postcode_vs_municipal"] == 0.857


INDEX = [{"ref_area": "ITD", "purchase": "ALL", "period": p, "index_2025": v, "provisional": p == "2026-Q2"}
         for p, v in (("2025-Q3", 100.9), ("2025-Q4", 101.7), ("2026-Q1", 102.9), ("2026-Q2", 104.8))]


def test_price_update_from_the_omi_semester_to_the_latest_quarter():
    update = price_update(INDEX, "2025/2", "ITD")
    assert update["factor"] == round(104.8 / 101.3, 4) and update["to"] == "2026 T2" and update["provisional"]
    assert price_update(INDEX, "2026/1", "ITD") is None  # semester not complete in the index
    assert ipab_area("NORD-EST", "BOLOGNA") == "ITD" and ipab_area("NORD-OVEST", "MILANO") == "ITC45"


def test_residential_valuation_is_brought_to_the_latest_quarter():
    update = price_update(INDEX, "2025/2", "ITD")
    base = build_valuation(property_record={"property_type": "residenziale", "surface_m2": 100, "condition": "Buono"}, zone=ZONE)
    updated = build_valuation(property_record={"property_type": "residenziale", "surface_m2": 100, "condition": "Buono"},
                              zone=ZONE, price_update=update)
    assert updated["range"]["mid"] == round(base["range"]["mid"] * update["factor"] / 1000) * 1000
    assert updated["adjustments"][-1]["label"].startswith("Aggiornamento prezzi Istat Nord-Est")
