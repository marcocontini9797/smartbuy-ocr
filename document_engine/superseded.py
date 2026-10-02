"""Replaced versions of a document: kept, but out of every check.

An agent can mark a document as replaced by a newer version of the same
document (``documents.superseded_by``). The row, its file and its facts stay
and the mark can be undone; what changes is that the replaced version no
longer takes part in cross-validation, the checklist, the valuation, the
agent's answers or the shared fascicolo. Without this, an old and a new
visura of the same unit would keep contradicting each other.
"""

from __future__ import annotations

from typing import Any, Iterable

# Same document under two names. Deliberately narrower than the similarity
# engine's aliases: an atto di provenienza is never a version of an atto di
# compravendita, even though both are notarial deeds.
_SYNONYMS = {
    "visura": "visura_catastale", "planimetria": "planimetria_catastale",
    "ape_energy_certificate": "ape", "ispezione_ipotecaria": "visura_ipotecaria",
    "titoli_edilizi": "titolo_edilizio", "agibilita": "certificato_agibilita",
}
_UNKNOWN_KINDS = {"", "altro", "unknown", "document", "none"}


def _family(document: dict[str, Any]) -> str | None:
    kind = str(document.get("document_type") or "").strip().casefold().replace(" ", "_")
    return None if kind in _UNKNOWN_KINDS else _SYNONYMS.get(kind, kind)


class SupersedeError(ValueError):
    """A replacement that must be refused, with the HTTP status to answer."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def is_superseded(document: dict[str, Any]) -> bool:
    return document.get("superseded_by") not in (None, "")


def current_documents(documents: Iterable[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [d for d in documents or [] if not is_superseded(d)]


def current_facts(facts: Iterable[dict[str, Any]] | None,
                  documents: Iterable[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Facts that do not come from a replaced document. Facts without a
    source document (entered by hand) are always kept."""
    hidden = {str(d["id"]) for d in documents or [] if is_superseded(d) and d.get("id") is not None}
    if not hidden:
        return list(facts or [])
    return [f for f in facts or [] if str(f.get("source_document_id")) not in hidden]


def drop_superseded(documents: Iterable[dict[str, Any]] | None,
                    facts: Iterable[dict[str, Any]] | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(documents, facts) as they count for the checks."""
    documents = list(documents or [])
    return current_documents(documents), current_facts(facts, documents)


def validate_supersede(older: dict[str, Any] | None, newer: dict[str, Any] | None) -> None:
    """Refuse anything but replacing a document with a current, analysed
    version of the same kind. Both rows must already belong to the same
    fascicolo (the caller loads them from it)."""
    if not older or not newer:
        raise SupersedeError(404, "Documento non trovato in questa pratica")
    if str(older.get("id")) == str(newer.get("id")):
        raise SupersedeError(422, "Un documento non può sostituire se stesso")
    kind_older, kind_newer = _family(older), _family(newer)
    if not kind_older or not kind_newer:
        raise SupersedeError(422, "Tipo di documento non riconosciuto: non si può stabilire una versione")
    if kind_older != kind_newer:
        raise SupersedeError(422, "Si può sostituire solo con un documento dello stesso tipo")
    if is_superseded(newer):
        raise SupersedeError(409, "La versione indicata è a sua volta già sostituita")
    if newer.get("processing_status") not in (None, "completed"):
        raise SupersedeError(409, "La versione indicata non ha un'analisi completata")
    if is_superseded(older) and str(older["superseded_by"]) != str(newer.get("id")):
        raise SupersedeError(409, "Il documento è già stato sostituito da un'altra versione")
