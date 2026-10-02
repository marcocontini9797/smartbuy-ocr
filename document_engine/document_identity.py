"""Identity layer on top of document_similarity.compare_documents.

Two pure, deterministic pieces, no network, no cost:

* adapt_extracted_fields: the extraction schemas and the similarity engine
  speak different dialects (``riferimento`` + ``data_visura`` versus
  ``riferimenti_catastali`` + ISO ``document_date``). This maps one to the
  other for the comparison view only, never touching the stored fields and
  never inventing a ``document_series_id``.
* resolve_document_identity: given a similarity result, says what a
  difference *means* (newer version of the same unit, an accessory unit, a
  document that belongs elsewhere...) instead of only that numbers changed.

Nothing here authorises a merge or a deletion: every verdict is a triage
signal and ``automatic_merge_allowed`` is always False.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date
from typing import Any

from document_engine.document_similarity import (
    VERSION as SIMILARITY_VERSION,
    _document_date,
    _text,
    _units,
)

IDENTITY_VERSION = "1.0"

_DATE_KEYS = ("document_date", "issue_date", "data_emissione")
# Extraction fields that carry the issue date of the document itself, in the
# order of preference. Upload/processing timestamps are deliberately absent.
_DATE_SOURCES = ("document_date", "issue_date", "data_emissione", "data_visura", "data_documento", "data_rilascio")
# Cellars, garages and parking spaces sold with a main unit (same set the
# checklist uses): compatible with being an accessory, not proof that they are.
_ACCESSORY_CATEGORIES = frozenset({"C/2", "C/6", "C/7"})
_NUMBER = re.compile(r"\d+(?:[.,/]\d+)*")
_DAY_FIRST = re.compile(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})")
_COMUNE_PREFIX = re.compile(r"^comune\s+di\s+", re.IGNORECASE)
_COMUNE_SUFFIX = re.compile(r"\s*\(\s*(?:[A-Za-z]{2}|[A-Za-z]\d{3})\s*\)\s*$")

VERDICTS = (
    "out_of_scope",
    "exact_duplicate",
    "newer_version_candidate",
    "likely_same_document",
    "same_unit_different_document_types",
    "same_unit_conflict",
    "same_unit_unresolved",
    "ancillary_unit_candidate",
    "unit_outside_expected",
    "neither_matches_expected",
    "different_units_expectation_unknown",
    "overlapping_units_review",
    "identity_unresolved",
)


def parse_issue_date(value: Any) -> date | None:
    """ISO, or day-first dd/mm/yyyy, dd-mm-yyyy, dd.mm.yyyy (Italian documents).
    Two-digit years and every other shape are refused rather than guessed."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass
    match = _DAY_FIRST.fullmatch(text)
    if not match:
        return None
    day, month, year = (int(g) for g in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def normalize_comune_name(value: Any) -> Any:
    """"BOLOGNA (BO)" and "Comune di Bologna" are the same municipality as
    "Bologna". Only a leading "Comune di" and a trailing province/cadastral
    code in brackets are removed; the name is never mapped to a code."""
    if not isinstance(value, str):
        return value
    text = _COMUNE_SUFFIX.sub("", _COMUNE_PREFIX.sub("", value.strip())).strip()
    return text or value


def _normalized_records(records: Any) -> Any:
    if not isinstance(records, list):
        return records
    result = []
    for record in records:
        if isinstance(record, dict) and isinstance(_plain(record.get("comune")), str):
            record = {**record, "comune": normalize_comune_name(_plain(record["comune"]))}
        result.append(record)
    return result


def _plain(value: Any) -> Any:
    return value["valore"] if isinstance(value, dict) and "valore" in value else (
        value["value"] if isinstance(value, dict) and "value" in value else value)


def adapt_extracted_fields(fields: dict[str, Any] | None) -> dict[str, Any]:
    """Comparison view of extracted fields. Returns a new dict; the input is
    never modified."""
    adapted = dict(fields) if isinstance(fields, dict) else {}

    reference = _plain(adapted.get("riferimento"))
    if (not adapted.get("riferimenti_catastali") and isinstance(reference, dict)
            and any(_plain(v) not in (None, "") for v in reference.values())):
        adapted["riferimenti_catastali"] = [dict(reference)]
    if isinstance(adapted.get("riferimenti_catastali"), list):
        adapted["riferimenti_catastali"] = _normalized_records(adapted["riferimenti_catastali"])

    # Rewrite parseable non-ISO dates to ISO in place so the engine does not
    # call a perfectly good "13/05/2025" invalid; unparseable ones stay as
    # they are and are reported by the engine as invalid.
    parsed_dates: set[date] = set()
    has_unreadable = False
    for key in _DATE_SOURCES:
        raw = _plain(adapted.get(key))
        if raw in (None, ""):
            continue
        parsed = parse_issue_date(raw)
        if parsed is None:
            has_unreadable = True
            continue
        parsed_dates.add(parsed)
        if key in _DATE_KEYS:
            adapted[key] = parsed.isoformat()
    # One unambiguous issue date only: several different ones, or one we could
    # not read, are left for the engine to report instead of being resolved here.
    if len(parsed_dates) == 1 and not has_unreadable and "document_date" not in adapted:
        adapted["document_date"] = next(iter(parsed_dates)).isoformat()
    return adapted


def _date_components(value: date | None) -> set[str]:
    if value is None:
        return set()
    return {str(value.day), f"{value.day:02d}", str(value.month), f"{value.month:02d}", str(value.year)}


def _numeric_changes_follow_dates(a: dict, b: dict, date_a: date | None, date_b: date | None) -> bool:
    """True only when every changed numeric token of the OCR text is a
    component of the document's own issue date. A changed surface or
    parcel number is not a date component, so it stays unexplained."""
    text_a, text_b = a.get("ocr_text"), b.get("ocr_text")
    if not (date_a and date_b and date_a != date_b and isinstance(text_a, str) and isinstance(text_b, str)):
        return False
    tokens_a, tokens_b = Counter(_NUMBER.findall(_text(text_a))), Counter(_NUMBER.findall(_text(text_b)))
    removed, added = tokens_a - tokens_b, tokens_b - tokens_a
    if not (removed or added):
        return False
    return (set(removed) <= _date_components(date_a)) and (set(added) <= _date_components(date_b))


def _against_expected(doc: dict, expected: dict) -> str:
    units, incomplete = _units(doc)
    if incomplete or not units:
        return "unknown"
    if units.keys() & expected.keys():
        return "matches"
    # A municipal name and a cadastral code cannot be equated without an
    # official mapping, so they are not evidence of a different unit either.
    if any(d[0][0] != e[0][0] for d in units for e in expected):
        return "unknown"
    doc_categories = {c for cats in units.values() for c in cats}
    expected_categories = {c for cats in expected.values() for c in cats}
    expected_is_accessory = bool(expected_categories) and expected_categories <= _ACCESSORY_CATEGORIES
    if doc_categories and doc_categories <= _ACCESSORY_CATEGORIES and not expected_is_accessory:
        return "accessory"
    return "other"


def resolve_document_identity(similarity: dict, document_a: dict, document_b: dict, *,
                              expected_units: list[dict[str, Any]] | None = None,
                              today: date | None = None) -> dict:
    """What the similarity result means. ``document_a``/``document_b`` must be
    the same dicts passed to compare_documents (a = the one already on file,
    b = the new one, matching ``similarity["version"]["newer"]``)."""
    today = today or date.today()
    relation = similarity.get("identity", {}).get("relation", "unknown")
    status = similarity.get("status")
    result: dict[str, Any] = {
        "identity_version": IDENTITY_VERSION, "similarity_version": similarity.get("engine_version", SIMILARITY_VERSION),
        "verdict": "identity_unresolved", "unit_relation": relation, "newer": None, "lineage": None,
        "expected_unit": None, "explained": [], "open_conflicts": [], "reasons": [],
        "requires_review": True, "automatic_merge_allowed": False,
    }

    if status == "out_of_scope":
        result.update(verdict="out_of_scope", reasons=list(similarity.get("reasons", [])))
        return result
    if similarity.get("duplicate_exact"):
        result.update(verdict="exact_duplicate", requires_review=bool(similarity.get("requires_review")))
        return result

    date_a, state_a = _document_date(document_a)
    date_b, state_b = _document_date(document_b)
    conflicts = [dict(c) for c in similarity.get("conflicts", [])]
    if _numeric_changes_follow_dates(document_a, document_b, date_a, date_b):
        before = len(conflicts)
        conflicts = [c for c in conflicts if c.get("kind") != "numeric_change_requires_reading"]
        if len(conflicts) < before:
            result["explained"].append("numeric_changes_match_issue_dates")
    result["open_conflicts"] = [c.get("field") or c.get("kind") for c in conflicts]
    same_type = similarity.get("scores", {}).get("type") == 1.0

    if relation == "same_units":
        if not same_type:
            result.update(verdict="same_unit_different_document_types", requires_review=bool(conflicts))
        elif date_a and date_b and date_a != date_b:
            if max(date_a, date_b) > today:
                result.update(verdict="same_unit_unresolved")
                result["reasons"].append("future_issue_date")
            else:
                explicit = status == "same_document_updated"
                result.update(verdict="newer_version_candidate", newer="a" if date_a > date_b else "b",
                              lineage="explicit_series" if explicit else "inferred_from_unit_type_and_date")
                if not explicit:
                    result["reasons"].append("no_explicit_series_lineage_is_inferred")
        elif conflicts:
            result.update(verdict="same_unit_conflict")
        elif status == "similar":
            result.update(verdict="likely_same_document", requires_review=False)
        else:
            result.update(verdict="same_unit_unresolved")
        for state in (state_a, state_b):
            if state in {"invalid", "inconsistent"}:
                result["reasons"].append(f"issue_date_{state}")
        return result

    if relation == "different_units":
        if not expected_units:
            result.update(verdict="different_units_expectation_unknown")
            return result
        expected, expected_incomplete = _units({"extracted_fields": {"riferimenti_catastali": expected_units}})
        if expected_incomplete or not expected:
            result.update(verdict="different_units_expectation_unknown")
            result["reasons"].append("expected_unit_incomplete")
            return result
        placed = {"a": _against_expected(document_a, expected), "b": _against_expected(document_b, expected)}
        result["expected_unit"] = placed
        values = set(placed.values())
        if "unknown" in values:
            result.update(verdict="different_units_expectation_unknown")
        elif values == {"matches", "accessory"}:
            result.update(verdict="ancillary_unit_candidate")
            result["reasons"].append("accessory_category_not_proof_of_same_building")
        elif "matches" in values:
            result.update(verdict="unit_outside_expected")
        else:
            result.update(verdict="neither_matches_expected")
        return result

    if relation == "overlapping_units":
        result.update(verdict="overlapping_units_review")
        return result

    for label, doc in (("a", document_a), ("b", document_b)):
        units, incomplete = _units(doc)
        if incomplete:
            result["reasons"].append(f"document_{label}_units_incomplete")
        elif not units:
            result["reasons"].append(f"document_{label}_units_missing")
    return result
