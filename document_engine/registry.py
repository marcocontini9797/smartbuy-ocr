"""Turn Openapi Catasto answers into SmartBuy data.

- the street and house number to search, from the free-text address;
- the cadastral units found at an address;
- a "visura_catastale" document (owners, shares, category, rent) from the prospetto;
- a "visura_ipotecaria" document and a plain summary from the list of notes of
  a mortgage inspection, so the existing checklist and red flags use them.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

# Indicative list prices (+VAT) of the Openapi services, shown before each purchase.
PRICES_EUR = {"immobili": 0.30, "prospetto": 0.30, "visura_pdf": 1.90, "ispezione": 23.70}
SOURCE = "Openapi – Catasto e Conservatoria (Agenzia delle Entrate)"

_TOPONYMS = r"(via|viale|v\.le|piazza|p\.za|p\.zza|piazzale|largo|corso|c\.so|vicolo|strada|str\.|borgo|galleria|lungo\w*|contrada|localit[aà]|frazione|salita|vico|traversa)"
_PREJUDICIAL = re.compile(r"PIGNORAMENT|SEQUESTR|DOMANDA GIUDIZIALE|FALLIMENT|LIQUIDAZIONE GIUDIZIALE|IPOTECA|DECRETO INGIUNTIVO|ARRESTO", re.I)
_SEVERE = re.compile(r"PIGNORAMENT|SEQUESTR|DOMANDA GIUDIZIALE|FALLIMENT|LIQUIDAZIONE GIUDIZIALE", re.I)
_CANCEL = re.compile(r"CANCELLAZIONE|RESTRIZIONE|ESTINZIONE", re.I)
_TRANSFER = re.compile(r"COMPRAVENDITA|DONAZIONE|SUCCESSIONE|ACCETTAZIONE.*EREDIT|DIVISIONE|PERMUTA|CONFERIMENTO|DECRETO DI TRASFERIMENTO", re.I)


def split_address(address: str) -> tuple[str, str | None]:
    """"Via dell'Indipendenza 12/A" -> ("DELL'INDIPENDENZA", "12")."""
    text = re.sub(r"\s+", " ", str(address or "")).strip(" ,")
    number = None
    match = re.search(r"[, ]\s*(\d+)\s*(?:/?\s*[A-Za-z])?\s*$", text)
    if match:
        number, text = match.group(1), text[:match.start()].strip(" ,")
    text = re.sub(rf"^{_TOPONYMS}\s+", "", text, flags=re.I)
    return text.upper(), number


def pick_address(candidates: list[dict], street: str) -> dict | None:
    """The candidate whose name matches the street best (exact, then contained)."""
    street = street.upper()
    def name(c: dict) -> str:
        return re.sub(rf"^{_TOPONYMS}\s+", "", str(c.get("indirizzo") or "").upper(), flags=re.I)
    return (next((c for c in candidates if name(c) == street), None)
            or next((c for c in candidates if street in name(c) or name(c) in street), None)
            or (candidates[0] if len(candidates) == 1 else None))


def units(result: dict | None) -> list[dict]:
    rows = []
    for item in ((result or {}).get("risultato") or {}).get("immobili") or []:
        rows.append({key: item.get(key) for key in ("id_immobile", "foglio", "particella", "subalterno", "sezione_urbana",
                                                    "indirizzo", "categoria", "classe", "consistenza", "rendita")})
    return rows


def _money(value: Any) -> float | None:
    if value in (None, ""):
        return None
    text = re.sub(r"[^\d,.\-]", "", str(value))
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def visura_fields(result: dict | None, comune: str, today: date | None = None) -> tuple[dict | None, list[dict]]:
    """(extracted_fields of a visura_catastale document, owners) from a prospetto answer."""
    items = ((result or {}).get("risultato") or {}).get("immobili") or []
    if not items:
        return None, []
    unit = items[0]
    owners = [{"nome": o.get("denominazione"), "cf": o.get("cf"), "diritto": o.get("proprieta"), "quota": o.get("quota")}
              for o in unit.get("intestatari") or []]
    fields = {
        "intestatari": [o["nome"] for o in owners if o["nome"]],
        "codici_fiscali_intestatari": [o["cf"] for o in owners if o["cf"]],
        "diritti_e_quote": "; ".join(f"{o['nome']}: {o['diritto'] or 'diritto'} {o['quota'] or ''}".strip() for o in owners) or None,
        "riferimento": {"comune": comune, "sezione": unit.get("sezione") or None, "foglio": str(unit.get("foglio") or "") or None,
                        "particella": str(unit.get("particella") or "") or None,
                        "subalterno": str(unit.get("subalterno") or "") or None, "categoria": unit.get("categoria"),
                        "classe": unit.get("classe"), "consistenza": unit.get("consistenza"),
                        "rendita_catastale_eur": _money(unit.get("rendita")), "indirizzo": unit.get("indirizzo")},
        "data_visura": (today or date.today()).isoformat(),
        "note_incertezza": [],
    }
    return fields, owners


def mortgage_summary(result: dict | None) -> dict:
    """Notes of the inspection, the prejudicial ones and the latest transfer of ownership."""
    notes = []
    for item in (((result or {}).get("risultato") or {}).get("risultato") or {}).get("immobili") or []:
        for note in item.get("note") or []:
            notes.append({key: note.get(key) for key in ("tipo_nota", "data_nota", "tipo_atto", "registro_generale",
                                                         "registro_particolare", "pubblico_ufficiale", "repertorio")})
    notes.sort(key=lambda n: _date_key(n.get("data_nota")))
    prejudicial = [n for n in notes if _PREJUDICIAL.search(str(n.get("tipo_atto") or "")) and not _CANCEL.search(str(n.get("tipo_atto") or ""))]
    cancellations = [n for n in notes if _CANCEL.search(str(n.get("tipo_atto") or ""))]
    transfers = [n for n in notes if _TRANSFER.search(str(n.get("tipo_atto") or ""))]
    severe = [n for n in prejudicial if _SEVERE.search(str(n.get("tipo_atto") or ""))]
    summary = {"notes": notes, "prejudicial": prejudicial, "cancellations": cancellations,
               "last_transfer": transfers[-1] if transfers else None, "severe": bool(severe)}
    summary["reading"] = (
        f"{len(severe)} formalità giudiziali (pignoramento/sequestro o simili): verifica legale prima di procedere." if severe else
        f"{len(prejudicial)} ipoteche o formalità iscritte" + (f", {len(cancellations)} annotazioni di cancellazione/restrizione" if cancellations else "")
        + ": verificare quali sono ancora attive." if prejudicial else
        "Nessuna ipoteca o formalità pregiudizievole nelle note trovate.")
    return summary


def mortgage_fields(summary: dict, riferimento: dict) -> dict:
    """extracted_fields of a visura_ipotecaria document for the existing red-flag rules."""
    kinds = []
    for note in summary["prejudicial"]:
        label = str(note.get("tipo_atto") or "").strip()
        if label and label not in kinds:
            kinds.append(label)
    return {"soggetti": [], "tipo_formalita": "; ".join(kinds) or "nessuna formalità pregiudizievole",
            "data_iscrizione": summary["prejudicial"][-1].get("data_nota") if summary["prejudicial"] else None,
            "riferimenti_catastali": [riferimento],
            # Cancellation is known only for notes explicitly annotated; otherwise it stays "not confirmed".
            "formalita_ancora_attiva": False if not summary["prejudicial"] else None,
            "note_incertezza": ["Stato di cancellazione delle ipoteche da confermare sulle singole note."] if summary["prejudicial"] else []}


def _date_key(value: Any) -> tuple:
    match = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", str(value or ""))
    if match:
        return int(match.group(3)), int(match.group(2)), int(match.group(1))
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(value or ""))
    return (int(match.group(1)), int(match.group(2)), int(match.group(3))) if match else (0, 0, 0)
