"""Property typologies and contracts handled by SmartBuy.

The typology decides the asset class (residenziale / commerciale), the OMI
quotation used for the value, the cadastral categories expected in the
documents and the transaction-volume series of the market context.
"""

from __future__ import annotations

from dataclasses import dataclass

_DWELLING = frozenset(f"A/{n}" for n in (1, 2, 3, 4, 5, 6, 7, 8, 9, 11))


@dataclass(frozen=True)
class Typology:
    key: str
    label: str
    asset: str                    # residenziale | commerciale
    omi_codes: tuple[str, ...]    # OMI cod_tip in order of preference; () = from the cadastral category
    categories: frozenset[str]    # cadastral categories consistent with the typology
    volume_series: str            # AdE NTN series for the market context
    volume_label: str


TYPOLOGIES: dict[str, Typology] = {t.key: t for t in (
    Typology("appartamento", "Appartamento", "residenziale", (), _DWELLING, "RES", "abitazioni"),
    Typology("villa", "Villa o villetta", "residenziale", ("1",), _DWELLING, "RES", "abitazioni"),
    Typology("box", "Box o posto auto", "residenziale", ("13", "16", "14", "15"), frozenset({"C/6", "C/7"}), "PER_BOX", "box e posti auto"),
    Typology("negozio", "Negozio o locale commerciale", "commerciale", ("5",), frozenset({"C/1", "C/3", "D/8"}),
             "TCO_NEG_LAB", "negozi e laboratori"),
    Typology("ufficio", "Ufficio", "commerciale", ("6", "18"), frozenset({"A/10", "D/5"}), "TCO_UFFICI", "uffici"),
    Typology("capannone", "Capannone o laboratorio", "commerciale", ("7", "8", "10"), frozenset({"C/3", "D/1", "D/7", "D/8"}),
             "PRO", "immobili produttivi"),
    Typology("magazzino", "Magazzino o deposito", "commerciale", ("9",), frozenset({"C/2", "C/3", "D/8"}),
             "TCO_DEPOSITI", "magazzini e depositi"),
    Typology("centro_commerciale", "Centro commerciale", "commerciale", ("17",), frozenset({"D/8"}),
             "TCO_D08", "fabbricati commerciali"),
)}
CONTRACTS = {"vendita": "Vendita", "affitto": "Affitto"}
DEFAULT_BY_ASSET = {"residenziale": "appartamento", "commerciale": "negozio"}


def typology_of(record: dict) -> Typology:
    """Typology of a property row; rows created before typologies fall back on the asset class."""
    key = record.get("typology") or DEFAULT_BY_ASSET.get(record.get("property_type") or "", "appartamento")
    return TYPOLOGIES.get(key, TYPOLOGIES["appartamento"])


def contract_of(record: dict) -> str:
    return record.get("contract") if record.get("contract") in CONTRACTS else "vendita"
