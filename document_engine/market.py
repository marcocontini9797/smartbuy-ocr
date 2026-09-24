"""Market activity around a property, from the AdE OMI transaction volumes (NTN).

Volumes are published per province, split between the provincial capital and
the rest of the province, per quarter. We report the last four quarters, the
change on the four before, and for homes the size class of the property.
Context only: volumes do not change the value range.
"""

from __future__ import annotations

from typing import Any

SOURCE = "Agenzia delle Entrate – OMI, volumi di compravendita (NTN)"
SERIES_BY_KIND = {"residenziale": ("RES", "abitazioni"), "commerciale": ("TCO_NEG_LAB", "negozi e laboratori")}
SIZE_CLASSES = ((50, "0_50", "fino a 50 m²"), (85, "50_85", "50–85 m²"), (115, "85_115", "85–115 m²"),
                (145, "115_145", "115–145 m²"), (float("inf"), "145_plus", "oltre 145 m²"))
TREND_THRESHOLD = 0.05


def _quarters(row: dict[str, Any]) -> list[tuple[str, float]]:
    """Definitive values, completed by provisional ones for later quarters."""
    merged = {**(row.get("ntn_provisional") or {}), **(row.get("ntn") or {})}
    return sorted(((period, float(value)) for period, value in merged.items()), key=lambda item: tuple(map(int, item[0].split("_"))))


def _label(period: str) -> str:
    year, quarter = period.split("_")
    return f"{quarter}° trim. {year}"


def _window(row: dict[str, Any]) -> dict[str, Any] | None:
    quarters = _quarters(row)
    if len(quarters) < 8:
        return None
    last, previous = quarters[-4:], quarters[-8:-4]
    total, before = sum(v for _, v in last), sum(v for _, v in previous)
    provisional = [p for p, _ in last if p not in (row.get("ntn") or {})]
    return {"last_12m": round(total), "previous_12m": round(before), "change": round((total - before) / before, 3) if before else None,
            "period": f"{_label(last[0][0])} – {_label(last[-1][0])}", "provisional": bool(provisional)}


def build_market_context(rows: list[dict[str, Any]], *, kind: str, capoluogo: bool, provincia: str,
                         comune: str | None, surface: float | None) -> dict[str, Any] | None:
    series, label = SERIES_BY_KIND.get(kind, SERIES_BY_KIND["residenziale"])
    by_series = {row["series"]: row for row in rows if row.get("capoluogo") == capoluogo}
    main = by_series.get(series)
    window = _window(main) if main else None
    if not window:
        return None
    scope = f"comune capoluogo ({comune.title()})" if capoluogo and comune else f"provincia di {provincia} esclusa la città capoluogo"
    result = {"scope": scope, "segment": label, **window, "source": SOURCE}
    history = _quarters(main)
    years: dict[str, float] = {}
    for period, value in history:
        years.setdefault(period[:4], 0.0)
        years[period[:4]] += value
    complete = {year: total for year, total in years.items() if sum(1 for p, _ in history if p.startswith(year)) == 4}
    result["yearly"] = [{"year": year, "ntn": round(total)} for year, total in sorted(complete.items())]

    if kind == "residenziale" and surface:
        _, code, size_label = next(item for item in SIZE_CLASSES if surface <= item[0])
        size_row = by_series.get(f"RES_{code}")
        size_window = _window(size_row) if size_row else None
        if size_window:
            result["size_class"] = {"label": size_label, **size_window,
                                    "share": round(size_window["last_12m"] / window["last_12m"], 3) if window["last_12m"] else None}

    change = window["change"]
    if change is None:
        result["reading"] = "Variazione non calcolabile."
    elif change <= -TREND_THRESHOLD:
        result["reading"] = (f"Compravendite in calo ({change:+.0%} sui 12 mesi precedenti): mercato che rallenta, "
                             "margine di trattativa per chi compra tendenzialmente più ampio.")
    elif change >= TREND_THRESHOLD:
        result["reading"] = (f"Compravendite in aumento ({change:+.0%} sui 12 mesi precedenti): mercato vivace, "
                             "margine di trattativa per chi compra tendenzialmente più stretto.")
    else:
        result["reading"] = f"Compravendite stabili ({change:+.0%} sui 12 mesi precedenti)."
    return result
