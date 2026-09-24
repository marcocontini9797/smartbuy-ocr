from document_engine.market import build_market_context


def _row(series, values, capoluogo=True, provisional=None):
    return {"series": series, "capoluogo": capoluogo, "ntn": values, "ntn_provisional": provisional or {}}


QUARTERS = {f"{y}_{q}": 100.0 for y in (2023, 2024) for q in (1, 2, 3, 4)}


def test_last_twelve_months_use_provisional_quarters_after_definitive_ones():
    rows = [_row("RES", QUARTERS, provisional={"2025_1": 120, "2025_2": 120, "2025_3": 120, "2025_4": 120})]
    result = build_market_context(rows, kind="residenziale", capoluogo=True, provincia="BO", comune="BOLOGNA", surface=None)
    assert result["last_12m"] == 480 and result["previous_12m"] == 400 and result["change"] == 0.2
    assert result["provisional"] and "in aumento" in result["reading"]
    assert result["period"] == "1° trim. 2025 – 4° trim. 2025"
    assert [y["year"] for y in result["yearly"]] == ["2023", "2024", "2025"]


def test_commercial_uses_shop_volumes_and_the_rest_of_the_province():
    rows = [_row("RES", QUARTERS, capoluogo=False),
            _row("TCO_NEG_LAB", {**QUARTERS, "2024_1": 40, "2024_2": 40, "2024_3": 40, "2024_4": 40}, capoluogo=False)]
    result = build_market_context(rows, kind="commerciale", capoluogo=False, provincia="BO", comune="IMOLA", surface=60)
    assert result["segment"] == "negozi e laboratori" and result["change"] == -0.6
    assert "esclusa la città capoluogo" in result["scope"] and "in calo" in result["reading"]


def test_size_class_share_for_homes():
    rows = [_row("RES", QUARTERS), _row("RES_50_85", {k: 40.0 for k in QUARTERS})]
    result = build_market_context(rows, kind="residenziale", capoluogo=True, provincia="BO", comune="BOLOGNA", surface=75)
    assert result["size_class"]["label"] == "50–85 m²" and result["size_class"]["share"] == 0.4


def test_missing_series_gives_no_context():
    assert build_market_context([], kind="residenziale", capoluogo=True, provincia="XX", comune=None, surface=80) is None
