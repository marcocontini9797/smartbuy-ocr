"""Domain-aware cross-validation of property facts across documents.

Every extracted value becomes a ``Claim`` tied to its source (a document when
known, otherwise the source type). Claims are normalized with Italian real
estate rules (catasto, superfici, nominativi, codice fiscale, indirizzi, APE)
and compared per field:

* the same document yielding different values is an *extraction* problem
  (``extraction_unstable``), not a conflict between documents;
* repeated extractions of one document count as one source, never as
  independent confirmations;
* different measures of the same thing (superficie utile vs commerciale) are
  compared with physiological margins (``compatible``) instead of equality.

Deterministic by design: no LLM is involved once values are extracted.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable, Iterable

from core.operational_models import CrossValidationFinding, stable_id


# ---------------------------------------------------------------------------
# Normalizers
# ---------------------------------------------------------------------------

_MONTHS = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
    "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}
_TITLES = {"sig", "sigra", "sigg", "dott", "dottssa", "dottsa", "ing", "arch", "geom", "avv", "prof", "sra", "sr", "signor", "signora"}
_ADDRESS_ABBREVIATIONS = {
    "v": "via", "vle": "viale", "p": "piazza", "pza": "piazza", "pzza": "piazza", "pzale": "piazzale",
    "c": "corso", "cso": "corso", "vlo": "vicolo", "str": "strada", "lgo": "largo", "lungot": "lungotevere",
}


def strip_accents(value: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", value) if not unicodedata.combining(ch))


def norm_text(value: Any) -> str:
    text = strip_accents(str(value)).casefold()
    text = re.sub(r"[^\w/]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_number(value: Any) -> float | None:
    """Parse Italian and international number formats: ``1.234,56``, ``92 mq``, ``€ 320.000``."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"-?\d[\d.,' ]*", str(value))
    if not match:
        return None
    raw = match.group(0).replace(" ", "").replace("'", "").rstrip(".,")
    if "," in raw and "." in raw:
        decimal_sep = "," if raw.rfind(",") > raw.rfind(".") else "."
        thousands_sep = "." if decimal_sep == "," else ","
        raw = raw.replace(thousands_sep, "").replace(decimal_sep, ".")
    elif "," in raw:
        # Italian decimal comma; several commas can only be thousands separators.
        raw = raw.replace(",", "") if raw.count(",") > 1 else raw.replace(",", ".")
    elif raw.count(".") > 1 or (raw.count(".") == 1 and len(raw.split(".")[1]) == 3):
        # Italian thousands dot: "320.000" -> 320000.
        raw = raw.replace(".", "")
    try:
        return float(raw)
    except ValueError:
        return None


def parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = strip_accents(str(value)).casefold().strip()
    match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if match:
        y, m, d = map(int, match.groups())
    else:
        match = re.search(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})", text)
        if match:
            d, m, y = map(int, match.groups())
            y += 2000 if y < 100 else 0
        else:
            match = re.search(r"(\d{1,2})\s+([a-z]+)\s+(\d{4})", text)
            if not match or match.group(2) not in _MONTHS:
                return None
            d, m, y = int(match.group(1)), _MONTHS[match.group(2)], int(match.group(3))
    try:
        return date(y, m, d)
    except ValueError:
        return None


def norm_catasto_id(value: Any) -> str | None:
    """Foglio/particella/subalterno: drop labels and leading zeros (``Fg. 0285`` -> ``285``)."""
    if value is None:
        return None
    text = norm_text(value)
    text = re.sub(r"^(foglio|fg|particella|part|mappale|mapp|map|subalterno|sub|n)\b\s*", "", text)
    text = text.replace(" ", "")
    if not text:
        return None
    return str(int(text)) if text.isdigit() else text.upper()


def norm_comune(value: Any) -> str | None:
    """``Bologna (BO)`` / ``BOLOGNA - BO`` / ``Comune di Bologna`` -> ``bologna``."""
    text = re.sub(r"\(\s*[A-Za-z]{2}\s*\)|[-,]\s*[A-Za-z]{2}\s*$", " ", str(value or ""))
    text = re.sub(r"^\s*comune\s+di\s+", "", norm_text(text))
    return text.strip() or None


def norm_categoria(value: Any) -> str | None:
    match = re.search(r"\b([A-F])\s*[/\-]?\s*0*(\d{1,2})\b", strip_accents(str(value or "")).upper())
    return f"{match.group(1)}/{int(match.group(2))}" if match else None


_ENERGY_CLASSES = ["A4", "A3", "A2", "A1", "A+", "B", "C", "D", "E", "F", "G"]


def norm_energy_class(value: Any) -> str | None:
    text = strip_accents(str(value or "")).upper()
    text = re.sub(r"CLASSE|ENERGETICA|[:\s]", "", text)
    match = re.search(r"A[1-4]|A\+{1,4}|[A-G]", text)
    if not match:
        return None
    klass = match.group(0)
    return "A+" if klass.startswith("A+") else klass


def energy_class_rank(klass: str) -> int:
    return _ENERGY_CLASSES.index(klass) if klass in _ENERGY_CLASSES else -1


_CF_ODD = {
    **dict(zip("0123456789", [1, 0, 5, 7, 9, 13, 15, 17, 19, 21])),
    **dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ", [1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 2, 4, 18, 20, 11, 3, 6, 8, 12, 14, 16, 10, 22, 25, 24, 23])),
}
_CF_PATTERN = re.compile(r"\b[A-Z]{6}[0-9LMNPQRSTUV]{2}[ABCDEHLMPRST][0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{3}[A-Z]\b")


def codice_fiscale_valid(value: str) -> bool:
    """Checksum of an Italian personal codice fiscale (omocodia supported)."""
    cf = re.sub(r"\s", "", str(value or "")).upper()
    if not _CF_PATTERN.fullmatch(cf):
        return False
    total = 0
    for index, char in enumerate(cf[:15]):
        if index % 2 == 0:
            total += _CF_ODD[char]
        else:
            total += int(char) if char.isdigit() else ord(char) - ord("A")
    return chr(ord("A") + total % 26) == cf[15]


def find_codici_fiscali(value: Any) -> list[str]:
    return _CF_PATTERN.findall(strip_accents(str(value or "")).upper()) if value else []


def norm_person(value: Any) -> frozenset[str]:
    """Order-insensitive token set of a name: ``ROSSI Giovanni`` == ``Sig. Giovanni Rossi``."""
    text = strip_accents(str(value or "")).upper()
    text = _CF_PATTERN.sub(" ", text)
    text = re.split(r"\b(NATO|NATA|C\.?F\.?|CODICE FISCALE|PROPRIETA|PER LA QUOTA|QUOTA|RESIDENTE)\b", text)[0]
    tokens = [t for t in re.findall(r"[A-Z']+", text) if len(t) > 1]
    return frozenset(t for t in tokens if t.casefold().replace("'", "") not in _TITLES)


def norm_people(value: Any) -> frozenset[frozenset[str]]:
    items = value if isinstance(value, (list, tuple, set)) else re.split(r";|\n|\be\b", str(value or ""))
    return frozenset(p for p in (norm_person(item) for item in items) if p)


_ADDRESS_UNIT = re.compile(r"\b(interno|int|scala|sc|piano|p\.?t|lotto|edificio)\b\.?\s*\w*", re.IGNORECASE)


def norm_address(value: Any) -> tuple[str, str | None] | None:
    """(via, civico): unit details such as ``interno 3`` or ``piano 2`` are not the civico."""
    text = norm_text(_ADDRESS_UNIT.sub(" ", strip_accents(str(value or ""))))
    if not text:
        return None
    tokens = [_ADDRESS_ABBREVIATIONS.get(t, t) for t in text.replace("/", " / ").split()]
    tokens = [t for t in tokens if t not in {"n", "num", "civico", "c"}]
    number = None
    for index in range(len(tokens) - 1, -1, -1):
        if re.fullmatch(r"\d+[a-z]?", tokens[index]):
            number = tokens[index]
            tokens = tokens[:index]
            break
    street = " ".join(t for t in tokens if t != "/")
    return (street, number) if street else None


_FULL_OWNERSHIP = ("proprieta esclusiva", "piena proprieta", "proprieta per 1/1", "1/1", "intera proprieta", "100%")


def parse_quota(value: Any) -> float | None:
    text = norm_text(value)
    if not text:
        return None
    if any(marker in text for marker in _FULL_OWNERSHIP):
        return 1.0
    match = re.search(r"(\d+)\s*/\s*(\d+)", text)
    if match and int(match.group(2)):
        return int(match.group(1)) / int(match.group(2))
    return None


# ---------------------------------------------------------------------------
# Field specifications
# ---------------------------------------------------------------------------

EQUAL, COMPATIBLE, DIFFERENT = "equal", "compatible", "different"
Comparator = Callable[[Any, Any], tuple[str, str]]


def _exact(a: Any, b: Any) -> tuple[str, str]:
    return (EQUAL, "") if a == b else (DIFFERENT, "")


def _numeric(tolerance: float, unit: str = "") -> Comparator:
    def compare(a: float, b: float) -> tuple[str, str]:
        if a == b:
            return EQUAL, ""
        diff = abs(a - b) / max(abs(a), abs(b), 1e-9)
        if diff <= tolerance:
            return COMPATIBLE, f"Differenza del {diff:.1%}, entro la tolleranza del {tolerance:.0%}{unit}"
        return DIFFERENT, f"Differenza del {diff:.1%}"
    return compare


def _people(a: frozenset, b: frozenset) -> tuple[str, str]:
    if a == b:
        return EQUAL, ""
    unmatched = [p for p in a if not any(p <= q or q <= p for q in b)]
    unmatched += [q for q in b if not any(q <= p or p <= q for p in a)]
    if not unmatched:
        return COMPATIBLE, "Stessi soggetti, nominativi scritti in forma parziale in una fonte"
    return DIFFERENT, "Soggetti non coincidenti: " + ", ".join(" ".join(sorted(p)).title() for p in unmatched)


def _address(a: tuple, b: tuple) -> tuple[str, str]:
    (street_a, num_a), (street_b, num_b) = a, b
    same_street = street_a == street_b or set(street_a.split()) <= set(street_b.split()) or set(street_b.split()) <= set(street_a.split())
    if not same_street:
        return DIFFERENT, "Via diversa"
    if num_a and num_b and num_a != num_b:
        return DIFFERENT, f"Numero civico diverso ({num_a} / {num_b})"
    return (EQUAL, "") if (street_a, num_a) == (street_b, num_b) else (COMPATIBLE, "Civico presente in una sola fonte o via abbreviata")


def _energy(a: str, b: str) -> tuple[str, str]:
    if a == b:
        return EQUAL, ""
    gap = abs(energy_class_rank(a) - energy_class_rank(b))
    return DIFFERENT, f"Classi distanti {gap} livell{'o' if gap == 1 else 'i'}"


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    severity: str
    normalize: Callable[[Any], Any]
    compare: Comparator = _exact
    display: Callable[[Any], str] = str


def _show_people(value: frozenset) -> str:
    return "; ".join(" ".join(sorted(p)).title() for p in sorted(value, key=sorted))


def _show_number(unit: str) -> Callable[[float], str]:
    return lambda v: f"{v:,.2f}".rstrip("0").rstrip(".").replace(",", "X").replace(".", ",").replace("X", ".") + unit


SPECS: dict[str, FieldSpec] = {spec.key: spec for spec in [
    FieldSpec("catasto.comune", "Comune", "high", norm_comune, display=lambda v: v.title()),
    FieldSpec("catasto.sezione", "Sezione catastale", "medium", norm_catasto_id),
    FieldSpec("catasto.foglio", "Foglio", "high", norm_catasto_id),
    FieldSpec("catasto.particella", "Particella", "high", norm_catasto_id),
    FieldSpec("catasto.subalterno", "Subalterno", "high", norm_catasto_id),
    FieldSpec("catasto.categoria", "Categoria catastale", "high", norm_categoria),
    FieldSpec("catasto.classe", "Classe catastale", "medium", norm_catasto_id),
    FieldSpec("catasto.consistenza", "Consistenza", "medium", parse_number, _numeric(0.0), _show_number("")),
    FieldSpec("catasto.rendita_eur", "Rendita catastale", "medium", parse_number, _numeric(0.001), _show_number(" €")),
    FieldSpec("indirizzo", "Indirizzo", "medium", norm_address, _address, lambda v: " ".join(x for x in v if x).title()),
    FieldSpec("proprietari", "Proprietari / intestatari", "high", norm_people, _people, _show_people),
    FieldSpec("codici_fiscali", "Codici fiscali intestatari", "high",
              lambda v: frozenset(find_codici_fiscali(" ".join(v) if isinstance(v, list) else v)) or None,
              _exact, lambda v: ", ".join(sorted(v))),
    FieldSpec("quota_proprieta", "Quota di proprietà", "high", parse_quota, _numeric(0.0), lambda v: f"{v:.0%}"),
    FieldSpec("classe_energetica", "Classe energetica", "medium", norm_energy_class, _energy),
    FieldSpec("epgl", "EPgl (kWh/m² anno)", "low", parse_number, _numeric(0.02), _show_number("")),
    FieldSpec("superficie_utile_mq", "Superficie utile", "medium", parse_number, _numeric(0.03, ""), _show_number(" m²")),
    FieldSpec("superficie_commerciale_mq", "Superficie commerciale", "medium", parse_number, _numeric(0.03), _show_number(" m²")),
    FieldSpec("superficie_catastale_mq", "Superficie catastale", "medium", parse_number, _numeric(0.03), _show_number(" m²")),
    FieldSpec("prezzo_eur", "Prezzo", "high", parse_number, _numeric(0.0), _show_number(" €")),
    FieldSpec("canone_mensile_eur", "Canone mensile", "high", parse_number, _numeric(0.0), _show_number(" €")),
]}


# Fact names / document paths -> canonical field. Riferimenti catastali are
# exploded into their components before this lookup.
ALIASES = {
    "energy_class": "classe_energetica", "classe_energetica": "classe_energetica", "classe": "classe_energetica",
    "epgl": "epgl", "epgl_kwh_mq_anno": "epgl",
    "intestatari": "proprietari", "owners": "proprietari", "owner": "proprietari", "proprietari": "proprietari",
    "parte_venditrice": "proprietari", "promittente_venditore": "proprietari", "locatore": "proprietari", "avente_causa": "proprietari",
    "diritti_e_quote": "quota_proprieta", "quota": "quota_proprieta",
    "superficie_utile_mq": "superficie_utile_mq", "surface_useful_m2": "superficie_utile_mq",
    "superficie_dichiarata_mq": "superficie_commerciale_mq", "superficie_commerciale_mq": "superficie_commerciale_mq",
    "superficie_commerciale_considerata_mq": "superficie_commerciale_mq", "surface_m2": "superficie_commerciale_mq",
    "superficie_catastale_mq": "superficie_catastale_mq",
    "codici_fiscali_intestatari": "codici_fiscali",
    "prezzo_eur": "prezzo_eur", "asking_price": "prezzo_eur", "price": "prezzo_eur",
    "canone_mensile_eur": "canone_mensile_eur",
    "address": "indirizzo", "indirizzo": "indirizzo",
    "comune": "catasto.comune", "city": "catasto.comune", "foglio": "catasto.foglio", "particella": "catasto.particella",
    "mappale": "catasto.particella", "subalterno": "catasto.subalterno", "sub": "catasto.subalterno",
    "sezione": "catasto.sezione", "categoria": "catasto.categoria", "category": "catasto.categoria",
    "classe_catastale": "catasto.classe", "consistenza": "catasto.consistenza",
    "rendita_catastale_eur": "catasto.rendita_eur", "rendita_catastale": "catasto.rendita_eur", "rendita": "catasto.rendita_eur",
}
_RIFERIMENTO_KEYS = {"riferimento", "riferimenti", "riferimenti_catastali", "cadastral", "riferimento_catastale"}
_RIFERIMENTO_PARTS = {
    "comune": "catasto.comune", "sezione": "catasto.sezione", "foglio": "catasto.foglio", "particella": "catasto.particella",
    "subalterno": "catasto.subalterno", "categoria": "catasto.categoria", "classe": "catasto.classe",
    "consistenza": "catasto.consistenza", "rendita_catastale_eur": "catasto.rendita_eur", "rendita_catastale": "catasto.rendita_eur",
    "indirizzo": "indirizzo",
}
# Superficie measures that are legitimately different: utile (APE) vs commerciale.
_SURFACE_RATIO_RANGE = (0.60, 1.0)


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------

@dataclass
class Claim:
    field: str
    raw: Any
    normalized: Any
    source_key: str
    source_label: str
    fact_id: str | None = None
    document_type: str | None = None
    confidence: float | None = None
    page: Any = None
    source_text: str | None = None
    evidence_ids: list[str] = field(default_factory=list)


def _unwrap(value: Any) -> Any:
    if isinstance(value, dict) and set(value) & {"value", "valore"}:
        return value.get("value", value.get("valore"))
    return value


def _float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _expand(name: str, value: Any) -> Iterable[tuple[str, Any]]:
    """Yield (canonical_field, raw_value) pairs for one extracted name/value."""
    key = name.strip().casefold()
    value = _unwrap(value)
    if key in _RIFERIMENTO_KEYS:
        for item in value if isinstance(value, list) else [value]:
            if isinstance(item, dict):
                for part, canonical in _RIFERIMENTO_PARTS.items():
                    part_value = _unwrap(item.get(part))
                    if part_value not in (None, "", []):
                        yield canonical, part_value
        return
    canonical = ALIASES.get(key)
    if canonical and value not in (None, "", []):
        yield canonical, value


def _claim(canonical: str, raw: Any, **meta: Any) -> Claim | None:
    spec = SPECS.get(canonical)
    if spec is None:
        return None
    try:
        normalized = spec.normalize(raw)
    except Exception:
        normalized = None
    if normalized in (None, "", frozenset()):
        return None
    return Claim(field=canonical, raw=raw, normalized=normalized, **meta)


HUMAN_VERIFIED = {"verified", "corrected"}


def effective_facts(facts: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply the agent's verdicts: they override the AI readings of the same document.

    * rejected facts are dropped;
    * if a document has a confirmed/corrected fact for a field, its other
      (unverified) readings of that field are dropped and the verified value is used.
    """
    kept = [fact for fact in facts if fact.get("verification_status") != "rejected"]
    verified_keys = {
        (fact.get("source_document_id"), fact.get("fact_name"))
        for fact in kept if fact.get("verification_status") in HUMAN_VERIFIED
    }
    result = []
    for fact in kept:
        key = (fact.get("source_document_id"), fact.get("fact_name"))
        if fact.get("verification_status") in HUMAN_VERIFIED:
            verified = fact.get("verified_value")
            result.append({**fact, "fact_value": verified if verified is not None else fact.get("fact_value"),
                           "confidence_score": 1.0})
        elif key not in verified_keys:
            result.append(fact)
    return result


def claims_from_facts(facts: Iterable[dict[str, Any]], provenance: dict[str, dict] | None = None) -> list[Claim]:
    claims: list[Claim] = []
    provenance = provenance or {}
    for fact in effective_facts(facts):
        name = str(fact.get("fact_name") or fact.get("field") or "")
        prov = provenance.get(str(fact.get("provenance_id"))) or fact.get("provenance") or {}
        document_id = fact.get("source_document_id") or prov.get("document_id")
        source_type = fact.get("source_type") or fact.get("source") or "unknown"
        source_key = f"doc:{document_id}" if document_id is not None else f"type:{source_type}"
        for canonical, raw in _expand(name, fact.get("fact_value", fact.get("value"))):
            claim = _claim(
                canonical, raw, source_key=source_key,
                source_label=prov.get("source_document") or (f"Documento {document_id}" if document_id is not None else str(source_type)),
                fact_id=str(fact["id"]) if fact.get("id") is not None else None,
                confidence=_float(fact.get("confidence_score", fact.get("confidence"))),
                page=prov.get("source_page"), source_text=prov.get("source_text"),
                evidence_ids=[str(item) for item in fact.get("evidence_ids") or []],
            )
            if claim:
                claims.append(claim)
    return claims


def claims_from_documents(documents: Iterable[dict[str, Any]]) -> list[Claim]:
    """Claims from each document's typed ``extracted_fields`` (schemas.py models)."""
    claims: list[Claim] = []
    for document in documents:
        fields = document.get("extracted_fields") or {}
        if not isinstance(fields, dict):
            continue
        document_id = document.get("id")
        for name, value in fields.items():
            # A buyer is not an owner: only seller-side parties feed "proprietari".
            if name in {"parte_acquirente", "promittente_acquirente", "conduttore", "dante_causa"}:
                continue
            for canonical, raw in _expand(name, value):
                claim = _claim(
                    canonical, raw, source_key=f"doc:{document_id}",
                    source_label=document.get("file_name") or f"Documento {document_id}",
                    document_type=document.get("document_type"),
                    confidence=_float(_field_confidence(value) if _field_confidence(value) is not None else document.get("extraction_confidence")),
                )
                if claim:
                    claims.append(claim)
    return claims


# The asking price is not a contract price, so it is never compared with atto/preliminare.
_PROPERTY_RECORD_FIELDS = {"address": "indirizzo", "city": "catasto.comune", "surface_m2": "superficie_commerciale_mq"}


def claims_from_property(record: dict[str, Any] | None) -> list[Claim]:
    """The property sheet entered by the agent is a source to check documents against."""
    claims: list[Claim] = []
    for name, canonical in _PROPERTY_RECORD_FIELDS.items():
        value = (record or {}).get(name)
        claim = _claim(canonical, value, source_key="type:property_record", source_label="Scheda immobile",
                       confidence=0.9) if value not in (None, "") else None
        if claim:
            claims.append(claim)
    return claims


def _field_confidence(value: Any) -> Any:
    return value.get("confidence") if isinstance(value, dict) else None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@dataclass
class _SourceValue:
    source_key: str
    claims: list[Claim]
    value: Any
    unstable: bool
    share: float

    @property
    def confidence(self) -> float:
        known = [c.confidence for c in self.claims if c.confidence is not None]
        base = max(known) if known else 0.7
        return base * self.share


def _collapse_source(spec: FieldSpec, claims: list[Claim]) -> _SourceValue:
    """One value per source: majority (confidence-weighted) among its extractions."""
    weights: Counter = Counter()
    for claim in claims:
        weights[_hashable(claim.normalized)] += max(claim.confidence if claim.confidence is not None else 0.5, 0.001)
    groups: list[list[Any]] = []
    for key in weights:
        for group in groups:
            if spec.compare(_unhash(group[0]), _unhash(key))[0] != DIFFERENT:
                group.append(key)
                break
        else:
            groups.append([key])
    best = max(groups, key=lambda g: sum(weights[k] for k in g))
    total = sum(weights.values()) or 1.0
    return _SourceValue(
        source_key=claims[0].source_key, claims=claims,
        value=_unhash(max(best, key=lambda k: weights[k])),
        unstable=len(groups) > 1, share=sum(weights[k] for k in best) / total,
    )


def _hashable(value: Any) -> Any:
    return ("__set__", value) if isinstance(value, frozenset) else value


def _unhash(value: Any) -> Any:
    return value[1] if isinstance(value, tuple) and value and value[0] == "__set__" else value


def _values_payload(spec: FieldSpec, claims: list[Claim]) -> list[dict[str, Any]]:
    return [{
        "value": claim.raw, "normalized": spec.display(claim.normalized), "source": claim.source_label,
        "source_key": claim.source_key, "document_type": claim.document_type, "fact_id": claim.fact_id,
        "confidence": claim.confidence, "page": claim.page, "source_text": claim.source_text,
    } for claim in claims]


def _finding(property_id: int, spec: FieldSpec, status: str, claims: list[Claim], *, severity: str,
             confidence: float, canonical: Any, detail: str, action: str | None) -> CrossValidationFinding:
    return CrossValidationFinding(
        finding_id=stable_id("cross-validation", property_id, spec.key, status, *sorted(c.source_key for c in claims)),
        property_id=property_id, field=spec.key, label=spec.label, status=status, severity=severity,
        confidence=round(confidence, 3), canonical_value=spec.display(canonical) if canonical is not None else None,
        values=_values_payload(spec, claims), sources=sorted({c.source_key for c in claims}),
        evidence_ids=sorted({e for c in claims for e in c.evidence_ids}), detail=detail, recommended_action=action,
    )


def _compare_field(property_id: int, spec: FieldSpec, claims: list[Claim]) -> list[CrossValidationFinding]:
    by_source: dict[str, list[Claim]] = defaultdict(list)
    for claim in claims:
        by_source[claim.source_key].append(claim)
    sources = [_collapse_source(spec, items) for items in by_source.values()]
    findings: list[CrossValidationFinding] = []

    for source in sources:
        if source.unstable:
            distinct = sorted({spec.display(c.normalized) for c in source.claims})
            findings.append(_finding(
                property_id, spec, "extraction_unstable", source.claims, severity=spec.severity,
                confidence=source.confidence, canonical=source.value,
                detail=f"Lo stesso documento ha prodotto valori diversi nelle estrazioni: {', '.join(distinct)}. "
                       f"Valore prevalente: {spec.display(source.value)}.",
                action="Verificare il valore sul documento originale e confermarlo",
            ))

    if len(sources) == 1:
        source = sources[0]
        if not source.unstable and source.source_key != "type:property_record":
            findings.append(_finding(
                property_id, spec, "insufficient_evidence", source.claims, severity="low",
                confidence=source.confidence, canonical=source.value,
                detail=f"Valore presente in una sola fonte ({source.claims[0].source_label}).",
                action="Acquisire una seconda fonte indipendente",
            ))
        return findings

    uncertain = [source for source in sources if source.unstable or source.confidence < 0.4]
    if uncertain:
        findings.append(_finding(
            property_id, spec, "attention", claims, severity=spec.severity,
            confidence=min(source.confidence for source in sources), canonical=None,
            detail="Il confronto comprende letture incerte o discordanti dello stesso documento. Non è ancora possibile confermare una contraddizione tra le fonti.",
            action="Rileggere e correggere i dati sulle fonti originali, poi ripetere il confronto",
        ))
        return findings

    reference = max(sources, key=lambda s: s.confidence)
    verdicts = [(s, *spec.compare(reference.value, s.value)) for s in sources if s is not reference]
    all_claims = [c for s in sources for c in s.claims]
    if any(v == DIFFERENT for _, v, _ in verdicts):
        details = [f"{s.claims[0].source_label}: {spec.display(s.value)}" + (f" ({d})" if d else "")
                   for s, v, d in verdicts if v == DIFFERENT]
        findings.append(_finding(
            property_id, spec, "conflict", all_claims, severity=spec.severity, confidence=0.0, canonical=None,
            detail=f"{reference.claims[0].source_label}: {spec.display(reference.value)} — " + "; ".join(details),
            action="Verificare le fonti e confermare il valore corretto",
        ))
    else:
        disbelief = 1.0
        for source in sources:
            disbelief *= 1 - min(source.confidence, 0.99)
        notes = [d for _, v, d in verdicts if v == COMPATIBLE and d]
        findings.append(_finding(
            property_id, spec, "compatible" if notes else "consistent", all_claims, severity="low",
            confidence=min(0.99, 1 - disbelief), canonical=reference.value,
            detail=(f"Valori concordanti in {len(sources)} fonti registrate; la concordanza non prova da sola la correttezza del dato." + (" " + " ".join(sorted(set(notes))) if notes else "")),
            action=None,
        ))
    return findings


def _surface_cross_measure(property_id: int, claims: list[Claim]) -> list[CrossValidationFinding]:
    utile = [c for c in claims if c.field == "superficie_utile_mq"]
    commerciale = [c for c in claims if c.field in {"superficie_commerciale_mq", "superficie_catastale_mq"}]
    if not utile or not commerciale:
        return []
    spec = SPECS["superficie_utile_mq"]
    u = max(utile, key=lambda c: c.confidence or 0).normalized
    k = max(commerciale, key=lambda c: c.confidence or 0).normalized
    if not k:
        return []
    ratio = u / k
    low, high = _SURFACE_RATIO_RANGE
    ok = low <= ratio <= high
    related = utile + commerciale
    return [CrossValidationFinding(
        finding_id=stable_id("cross-validation", property_id, "superficie.rapporto", *sorted({c.source_key for c in related})),
        property_id=property_id, field="superficie.rapporto", label="Superficie utile vs commerciale",
        status="compatible" if ok else "conflict", severity="low" if ok else "medium",
        confidence=0.8 if ok else 0.0, canonical_value=f"{ratio:.0%}",
        values=_values_payload(spec, related), sources=sorted({c.source_key for c in related}),
        detail=(f"La superficie utile è il {ratio:.0%} di quella commerciale/catastale "
                f"(intervallo fisiologico {low:.0%}–{high:.0%})."),
        recommended_action=None if ok else "Verificare la superficie con planimetria catastale e APE",
    )]


def _validity_checks(property_id: int, facts: Iterable[dict[str, Any]], documents: Iterable[dict[str, Any]],
                     today: date) -> list[CrossValidationFinding]:
    findings: list[CrossValidationFinding] = []
    texts: list[tuple[str, str, Any, str]] = []
    document_types = {str(d.get("id")): str(d.get("document_type") or "") for d in documents}
    for fact in facts:
        texts.append((f"doc:{fact.get('source_document_id')}", str(fact.get("fact_name")), _unwrap(fact.get("fact_value")), document_types.get(str(fact.get("source_document_id")), str(fact.get("fact_category") or ""))))
    for document in documents:
        for name, value in (document.get("extracted_fields") or {}).items():
            texts.append((f"doc:{document.get('id')}", name, _unwrap(value), str(document.get("document_type") or "")))

    seen_cf: set[str] = set()
    for source_key, name, value, document_type in texts:
        for cf in find_codici_fiscali(value):
            if cf in seen_cf:
                continue
            seen_cf.add(cf)
            if not codice_fiscale_valid(cf):
                findings.append(CrossValidationFinding(
                    finding_id=stable_id("validity", property_id, "codice_fiscale", cf), property_id=property_id,
                    field="codice_fiscale", label="Codice fiscale", status="invalid", severity="high", confidence=0.95,
                    canonical_value=cf, values=[{"value": cf, "source_key": source_key, "field": name}], sources=[source_key],
                    detail=f"Il codice fiscale {cf} non supera il controllo del carattere di controllo: probabile errore di lettura o trascrizione.",
                    recommended_action="Confrontare il codice fiscale con il documento d'identità del soggetto",
                ))

        key = name.casefold()
        parsed = parse_date(value) if isinstance(value, str) else None
        if parsed is None:
            continue
        if document_type in {"ape", "ape_energy_certificate"} and key == "data_scadenza" and parsed < today:
            findings.append(_date_finding(property_id, "ape.scadenza", "Scadenza APE", source_key, value, "invalid", "high",
                                          f"APE scaduto il {parsed:%d/%m/%Y}.", "Richiedere al proprietario un APE aggiornato e verificarne l’utilizzo nella pratica"))
        elif document_type in {"ape", "ape_energy_certificate"} and key == "data_emissione" and (today - parsed).days > 3652:
            findings.append(_date_finding(property_id, "ape.scadenza", "Scadenza APE", source_key, value, "invalid", "high",
                                          f"APE emesso il {parsed:%d/%m/%Y}: oltre i 10 anni di validità.", "Richiedere al proprietario un APE aggiornato e verificarne l’utilizzo nella pratica"))
        elif key == "data_visura" and (today - parsed).days > 90:
            findings.append(_date_finding(property_id, "visura.data", "Data visura", source_key, value, "attention", "medium",
                                          f"Visura del {parsed:%d/%m/%Y}, più vecchia di 90 giorni.", "Richiedere una visura aggiornata"))
    return findings


def _date_finding(property_id: int, field_key: str, label: str, source_key: str, value: Any, status: str,
                  severity: str, detail: str, action: str) -> CrossValidationFinding:
    return CrossValidationFinding(
        finding_id=stable_id("validity", property_id, field_key, source_key), property_id=property_id,
        field=field_key, label=label, status=status, severity=severity, confidence=0.95, canonical_value=str(value),
        values=[{"value": value, "source_key": source_key}], sources=[source_key], detail=detail, recommended_action=action,
    )


_STATUS_ORDER = {"conflict": 0, "invalid": 1, "extraction_unstable": 2, "attention": 3, "insufficient_evidence": 4, "compatible": 5, "consistent": 6}
_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _multiunit_sources(property_id, facts, documents):
    candidates = [(f"doc:{d.get('id')}", name, value) for d in documents for name,value in (d.get("extracted_fields") or {}).items()]
    candidates += [(f"doc:{f.get('source_document_id')}", str(f.get("fact_name")), _unwrap(f.get("fact_value"))) for f in effective_facts(facts) if f.get("source_document_id") is not None]
    excluded = {}
    for source,name,value in candidates:
        if name not in _RIFERIMENTO_KEYS or not isinstance(value,list):
            continue
        identities = {tuple(norm_catasto_id(_unwrap(item.get(k))) if item.get(k) is not None else "" for k in ("foglio","particella","subalterno")) for item in value if isinstance(item,dict)}
        identities.discard(("","",""))
        if len(identities)>1:
            excluded[source]=value
    findings = [CrossValidationFinding(
        finding_id=stable_id("cross-validation",property_id,"multiple_units",source), property_id=property_id,
        field="catasto.unita_multiple",label="Documento con più unità catastali",status="attention",severity="high",confidence=0.0,
        sources=[source],values=[{"source_key":source,"value":value}],
        detail="Il documento cita più unità. I suoi dati non sono stati confrontati come se appartenessero a un’unica unità.",
        recommended_action="Identifica l’unità oggetto della pratica e separa i dati delle eventuali pertinenze prima del confronto.",
    ) for source,value in excluded.items()]
    return set(excluded), findings


def cross_validate(
    property_id: int,
    facts: Iterable[dict[str, Any]] = (),
    documents: Iterable[dict[str, Any]] = (),
    provenance: dict[str, dict] | None = None,
    today: date | None = None,
    property_record: dict[str, Any] | None = None,
) -> list[CrossValidationFinding]:
    """Cross-validate every comparable field of a property, most urgent first."""
    facts, documents = list(facts), list(documents)
    # Persisted field verdicts take precedence over the document's original snapshot,
    # including rejection: never resurrect the raw value as a second reading.
    represented = {(str(f.get("source_document_id")), f.get("fact_name")) for f in facts if f.get("source_document_id") is not None}
    documents = [{**d, "extracted_fields": {k:v for k,v in (d.get("extracted_fields") or {}).items() if (str(d.get("id")), k) not in represented}} for d in documents]
    claims = claims_from_facts(facts, provenance) + claims_from_documents(documents) + claims_from_property(property_record)
    multiunit, scope_findings = _multiunit_sources(property_id, facts, documents)
    claims = [c for c in claims if c.source_key not in multiunit]
    by_field: dict[str, list[Claim]] = defaultdict(list)
    for claim in claims:
        by_field[claim.field].append(claim)
    findings: list[CrossValidationFinding] = []
    for key, items in by_field.items():
        findings += _compare_field(property_id, SPECS[key], items)
    findings += scope_findings
    findings += _surface_cross_measure(property_id, claims)
    validity = _validity_checks(property_id, effective_facts(facts), documents, today or date.today())
    findings += list({f.finding_id: f for f in validity}.values())
    findings.sort(key=lambda f: (_STATUS_ORDER.get(f.status, 9), _SEVERITY_ORDER.get(f.severity, 9), f.field))
    return findings


def summarize(findings: list[CrossValidationFinding]) -> dict[str, Any]:
    counts = Counter(f.status for f in findings)
    blocking = [f for f in findings if f.status in {"conflict", "invalid"} and f.severity == "high"]
    verified = counts["consistent"] + counts["compatible"]
    comparable = verified + counts["conflict"] + counts["insufficient_evidence"] + counts["extraction_unstable"]
    return {
        "consistent": counts["consistent"], "compatible": counts["compatible"], "conflicts": counts["conflict"],
        "invalid": counts["invalid"], "extraction_unstable": counts["extraction_unstable"],
        "attention": counts["attention"], "insufficient_evidence": counts["insufficient_evidence"],
        "blocking": len(blocking), "verified_ratio": round(verified / comparable, 3) if comparable else 0.0,
    }


# ---------------------------------------------------------------------------
# Double extraction
# ---------------------------------------------------------------------------

# Top-level extracted fields worth a second independent reading: an error here
# changes who sells, what is sold or at what price.
CRITICAL_EXTRACTION_FIELDS = {
    "riferimento", "riferimenti_catastali", "intestatari", "codici_fiscali_intestatari",
    "parte_venditrice", "promittente_venditore", "prezzo_eur", "canone_mensile_eur",
    "classe_energetica", "superficie_utile_mq", "superficie_dichiarata_mq", "superficie_catastale_mq",
    "data_emissione", "data_scadenza",
}


def _normalized_by_field(name: str, value: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for canonical, raw in _expand(name, value):
        claim = _claim(canonical, raw, source_key="-", source_label="-")
        if claim:
            out[canonical] = claim.normalized
    return out


def extraction_disagreements(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    """Critical fields where two independent readings of the same document differ.

    Returns {field: value from the second reading}. A value present in only one
    reading is not counted: that is a completeness issue, not a contradiction.
    """
    disagreements: dict[str, Any] = {}
    for name in sorted(CRITICAL_EXTRACTION_FIELDS & set(first) & set(second)):
        a, b = _normalized_by_field(name, first[name]), _normalized_by_field(name, second[name])
        for canonical in a.keys() & b.keys():
            if SPECS[canonical].compare(a[canonical], b[canonical])[0] == DIFFERENT:
                disagreements[name] = second[name]
                break
    return disagreements
