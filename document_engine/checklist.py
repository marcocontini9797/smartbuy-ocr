"""Sale checklist: which documents a residential purchase needs, their status,
and every issue found on them.

The whole property file is assembled from the extracted fields of all its
documents, so the red-flag rules that need several documents at once (e.g.
preliminare vs atto, donation in the chain of title) run here, together with
the cross-validation findings.

Status of each item, worst first:
    problem   - a high/critical red flag or a conflict/invalid finding
    to_check  - a medium red flag, an unstable reading or a date to renew
    missing   - no document of this kind yet
    verified  - present, nothing to report
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from core.operational_models import CrossValidationFinding
from fascicolo import Fascicolo, aggiungi_al_fascicolo
from document_engine.cross_validation import _expand, norm_categoria
from red_flags import run_all_red_flags
from schemas import SCHEMA_REGISTRY, TipoDocumento


@dataclass(frozen=True)
class ChecklistSpec:
    key: str
    title: str
    why: str
    provided_by: str
    requirement: str  # "required" | "recommended" | "condominium" | "leased"
    red_flag_categories: tuple[str, ...] = ()


# Residential sale. Operational checklist, not a statement of legal duties:
# the notary decides what is needed for the deed.
SALE_CHECKLIST: tuple[ChecklistSpec, ...] = (
    ChecklistSpec("visura_catastale", "Visura catastale", "Identifica l'immobile e chi ne risulta intestatario.",
                  "Venditore o tecnico", "required"),
    ChecklistSpec("planimetria", "Planimetria catastale", "Serve a verificare la conformità catastale, da dichiarare nell'atto.",
                  "Venditore", "required", ("conformita_catastale",)),
    ChecklistSpec("ape", "APE – Attestato di prestazione energetica", "È obbligatorio e va allegato all'atto di vendita.",
                  "Venditore", "required", ("ape",)),
    ChecklistSpec("visura_ipotecaria", "Visura ipotecaria", "Mostra ipoteche, pignoramenti e altre formalità che gravano sull'immobile.",
                  "Tecnico o notaio", "required", ("formalita_pregiudizievoli",)),
    ChecklistSpec("atto_di_provenienza", "Atto di provenienza", "Dimostra come il venditore è diventato proprietario (acquisto, donazione, successione).",
                  "Venditore", "required", ("provenienza",)),
    ChecklistSpec("titolo_edilizio", "Titoli edilizi", "Dimostrano che l'immobile è regolare dal punto di vista urbanistico.",
                  "Venditore o tecnico", "required", ("conformita_urbanistica", "vincoli")),
    ChecklistSpec("certificato_agibilita", "Agibilità", "Attesta che l'immobile è utilizzabile; se manca va dichiarato all'acquirente.",
                  "Venditore", "recommended", ("agibilita",)),
    ChecklistSpec("dichiarazione_conformita_impianti", "Conformità degli impianti", "Certifica impianto elettrico, gas e riscaldamento.",
                  "Venditore", "recommended", ("conformita_impianti",)),
    ChecklistSpec("relazione_tecnica_integrata", "Relazione tecnica integrata", "Un tecnico verifica la conformità catastale e urbanistica prima del rogito.",
                  "Tecnico incaricato", "recommended", ("conformita_tecnica",)),
    ChecklistSpec("regolamento_condominio", "Regolamento di condominio", "Regole e limiti d'uso che valgono anche per il nuovo proprietario.",
                  "Amministratore", "condominium"),
    ChecklistSpec("verbale_assemblea_condominio", "Ultimi verbali di assemblea", "Lavori deliberati, spese straordinarie e morosità da chiarire prima del rogito.",
                  "Amministratore", "condominium", ("condominio",)),
)

# Commercial unit (shop): agibilità and systems are needed to open a business,
# the building titles must show the commercial use, and a lease in place
# brings registration and the tenant's pre-emption right.
COMMERCIAL_CHECKLIST: tuple[ChecklistSpec, ...] = (
    ChecklistSpec("visura_catastale", "Visura catastale", "Identifica il locale, l'intestatario e la categoria catastale (per un negozio di solito C/1).",
                  "Venditore o tecnico", "required"),
    ChecklistSpec("planimetria", "Planimetria catastale", "Serve a verificare la conformità catastale, da dichiarare nell'atto.",
                  "Venditore", "required", ("conformita_catastale",)),
    ChecklistSpec("ape", "APE – Attestato di prestazione energetica", "Obbligatorio anche per i locali commerciali, va allegato all'atto.",
                  "Venditore", "required", ("ape",)),
    ChecklistSpec("visura_ipotecaria", "Visura ipotecaria", "Mostra ipoteche, pignoramenti e altre formalità sul locale.",
                  "Tecnico o notaio", "required", ("formalita_pregiudizievoli",)),
    ChecklistSpec("atto_di_provenienza", "Atto di provenienza", "Dimostra come il venditore è diventato proprietario.",
                  "Venditore", "required", ("provenienza",)),
    ChecklistSpec("titolo_edilizio", "Titoli edilizi e destinazione d'uso", "Dimostrano la regolarità urbanistica e che il locale ha destinazione commerciale.",
                  "Venditore o tecnico", "required", ("conformita_urbanistica", "vincoli")),
    ChecklistSpec("certificato_agibilita", "Agibilità", "Senza agibilità per uso commerciale può essere impossibile aprire un'attività.",
                  "Venditore", "required", ("agibilita",)),
    ChecklistSpec("dichiarazione_conformita_impianti", "Conformità degli impianti", "Necessaria per l'uso aperto al pubblico e per le licenze.",
                  "Venditore", "required", ("conformita_impianti",)),
    ChecklistSpec("contratto_locazione", "Contratto di locazione in essere", "Se il locale è affittato: canone, durata, registrazione e diritto di prelazione del conduttore.",
                  "Venditore", "leased", ("locazione",)),
    ChecklistSpec("relazione_tecnica_integrata", "Relazione tecnica integrata", "Un tecnico verifica conformità catastale, urbanistica e destinazione d'uso.",
                  "Tecnico incaricato", "recommended", ("conformita_tecnica",)),
    ChecklistSpec("regolamento_condominio", "Regolamento di condominio", "Può vietare o limitare alcune attività commerciali nel locale.",
                  "Amministratore", "condominium"),
    ChecklistSpec("verbale_assemblea_condominio", "Ultimi verbali di assemblea", "Lavori deliberati, spese straordinarie e morosità da chiarire prima del rogito.",
                  "Amministratore", "condominium", ("condominio",)),
)

# Cadastral categories consistent with each asset class.
_CATEGORIES = {
    "residenziale": {f"A/{n}" for n in (1, 2, 3, 4, 5, 6, 7, 8, 9, 11)},
    "commerciale": {"C/1", "C/3", "A/10", "D/5", "D/8"},
}

_TYPE_ALIASES = {"ape_energy_certificate": "ape", "visura": "visura_catastale", "planimetria_catastale": "planimetria",
                 "ispezione_ipotecaria": "visura_ipotecaria", "atto_provenienza": "atto_di_provenienza",
                 "titoli_edilizi": "titolo_edilizio", "agibilita": "certificato_agibilita"}


@dataclass
class ChecklistItem:
    key: str
    title: str
    why: str
    provided_by: str
    requirement: str
    applicable: bool
    status: str = "missing"
    documents: list[dict[str, Any]] = field(default_factory=list)
    issues: list[dict[str, Any]] = field(default_factory=list)
    action: str | None = None


def document_kind(value: Any) -> str:
    kind = str(value or "").strip().casefold().replace(" ", "_")
    return _TYPE_ALIASES.get(kind, kind)


def _agent_overrides(facts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """{document_id: {field: corrected value or _REMOVED}} from the agent's verdicts."""
    overrides: dict[str, dict[str, Any]] = {}
    for fact in facts:
        status = fact.get("verification_status")
        if status not in {"corrected", "rejected"} or fact.get("source_document_id") is None:
            continue
        value = fact.get("verified_value")
        if isinstance(value, dict) and set(value) == {"value"}:
            value = value["value"]
        overrides.setdefault(str(fact["source_document_id"]), {})[fact.get("fact_name")] = (
            _REMOVED if status == "rejected" else value)
    return overrides


_REMOVED = object()


def build_fascicolo(documents: list[dict[str, Any]], facts: list[dict[str, Any]] | None = None) -> Fascicolo:
    """Typed property file from the extracted fields of every analysed document,
    with the agent's corrections applied (a corrected field replaces the AI reading,
    a rejected one is removed)."""
    fascicolo = Fascicolo(tipo_transazione="acquisto")
    overrides = _agent_overrides(facts or [])
    for document in documents:
        kind = document_kind(document.get("document_type"))
        fields = document.get("extracted_fields")
        if isinstance(fields, dict) and str(document.get("id")) in overrides:
            fields = dict(fields)
            for name, value in overrides[str(document.get("id"))].items():
                if value is _REMOVED:
                    fields.pop(name, None)
                else:
                    fields[name] = value
        try:
            tipo = TipoDocumento(kind)
        except ValueError:
            continue
        model = SCHEMA_REGISTRY.get(tipo)
        if model is None or not isinstance(fields, dict):
            fascicolo.altri_documenti.append(kind)
            continue
        try:
            parsed = model.model_validate({**fields, "tipo_documento": tipo})
        except Exception:
            continue
        aggiungi_al_fascicolo(fascicolo, tipo, parsed, document_id=str(document.get("id")))
    return fascicolo


def _flag_issue(flag) -> dict[str, Any]:
    level = {"critica": "problem", "alta": "problem", "media": "to_check"}.get(flag.gravita, "info")
    return {"source": "regola", "category": flag.categoria, "level": level, "severity": flag.gravita, "title": flag.titolo,
            "detail": flag.descrizione, "action": flag.azione_consigliata, "reference": flag.riferimento}


def _finding_issue(finding: CrossValidationFinding) -> dict[str, Any] | None:
    if finding.status in {"conflict", "invalid"}:
        level = "problem" if finding.severity in {"high", "medium"} else "to_check"
    elif finding.status in {"extraction_unstable", "attention"}:
        level = "to_check"
    else:
        return None
    return {"source": "verifica", "category": finding.field, "level": level, "severity": finding.severity, "title": finding.label or finding.field,
            "detail": finding.detail, "action": finding.recommended_action, "reference": None}


def _category_issue(document: dict[str, Any], kind: str) -> dict[str, Any] | None:
    """A shop registered as a dwelling (or the reverse) is a problem for the sale."""
    fields = document.get("extracted_fields") or {}
    categories = set()
    for name in ("riferimento", "riferimenti_catastali"):
        for canonical, raw in _expand(name, fields.get(name)):
            if canonical == "catasto.categoria" and norm_categoria(raw):
                categories.add(norm_categoria(raw))
    wrong = sorted(c for c in categories if c not in _CATEGORIES[kind])
    if not wrong:
        return None
    expected = "commerciale (es. C/1)" if kind == "commerciale" else "abitativa (A/1–A/9)"
    return {"source": "verifica", "category": "categoria_catastale", "level": "problem", "severity": "high",
            "title": f"Categoria catastale {', '.join(wrong)} non coerente con l'immobile",
            "detail": f"Per un immobile {kind} ci si aspetta una categoria {expected}. "
                      "Una destinazione catastale diversa può impedire l'uso previsto o richiedere un cambio d'uso.",
            "action": "Verificare con un tecnico la destinazione d'uso legittima e l'eventuale cambio di categoria.",
            "reference": None}


def build_checklist(
    *,
    property_record: dict[str, Any],
    documents: list[dict[str, Any]],
    findings: list[CrossValidationFinding],
    facts: list[dict[str, Any]] | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    is_condominium = property_record.get("is_condominio")
    asset_kind = property_record.get("property_type") or "residenziale"
    specs = COMMERCIAL_CHECKLIST if asset_kind == "commerciale" else SALE_CHECKLIST
    items: dict[str, ChecklistItem] = {}
    for spec in specs:
        applicable = spec.requirement != "condominium" or is_condominium is not False
        items[spec.key] = ChecklistItem(spec.key, spec.title, spec.why, spec.provided_by, spec.requirement, applicable)

    kind_by_document: dict[str, str] = {}
    for document in documents:
        kind = document_kind(document.get("document_type"))
        kind_by_document[str(document.get("id"))] = kind
        if kind in items:
            items[kind].documents.append({"id": document.get("id"), "file_name": document.get("file_name"),
                                          "storage_path": document.get("storage_path")})

    general: list[dict[str, Any]] = []
    category_to_item = {category: spec.key for spec in specs for category in spec.red_flag_categories}
    for flag in run_all_red_flags(build_fascicolo(documents, facts)):
        issue = _flag_issue(flag)
        target = items.get(category_to_item.get(flag.categoria, ""))
        (target.issues if target else general).append(issue)

    for document in documents:
        issue = _category_issue(document, asset_kind)
        if issue:
            target = items.get("visura_catastale") if document_kind(document.get("document_type")) == "visura_catastale" else None
            (target.issues if target else general).append(issue)

    for finding in findings:
        issue = _finding_issue(finding)
        if issue is None:
            continue
        kinds = {kind_by_document.get(key.removeprefix("doc:")) for key in finding.sources if key.startswith("doc:")}
        targets = [items[kind] for kind in kinds if kind in items]
        for target in targets:
            target.issues.append(issue)
        if not targets:
            general.append(issue)

    for item in items.values():
        levels = {issue["level"] for issue in item.issues}
        if not item.documents:
            item.status = "missing"
            item.action = f"Richiedere: {item.title.lower()} ({item.provided_by.lower()})"
        elif "problem" in levels:
            item.status = "problem"
        elif "to_check" in levels:
            item.status = "to_check"
        else:
            item.status = "verified"
        if item.documents and item.issues and not item.action:
            item.action = next((issue["action"] for issue in item.issues if issue.get("action")), None)

    # Fixed, logical document order (as a notary checklist); non-applicable items last.
    ordered = sorted(items.values(), key=lambda i: not i.applicable)
    required = [i for i in items.values() if i.requirement == "required"]
    required_present = sum(1 for i in required if i.documents)
    problems = [i for i in items.values() if i.status == "problem"] + [g for g in general if g["level"] == "problem"]
    to_check = [i for i in items.values() if i.status == "to_check"] + [g for g in general if g["level"] == "to_check"]
    missing_required = [i for i in required if not i.documents]

    if problems:
        verdict, tone = "Ci sono problemi da risolvere prima della trattativa", "problem"
    elif missing_required:
        verdict, tone = f"Documentazione incompleta: mancano {len(missing_required)} documenti obbligatori", "missing"
    elif to_check:
        verdict, tone = "Quasi pronto: alcuni punti da ricontrollare", "to_check"
    else:
        verdict, tone = "Documentazione completa e coerente per la trattativa", "verified"

    return {
        "items": [asdict(item) for item in ordered],
        "general_issues": general,
        "summary": {
            "verdict": verdict,
            "tone": tone,
            "required_total": len(required),
            "required_present": required_present,
            "completeness": round(required_present / len(required), 3) if required else 0.0,
            "problems": len(problems),
            "to_check": len(to_check),
            "missing_required": len(missing_required),
        },
        "note": f"Checklist operativa per la compravendita di un immobile {asset_kind}: non sostituisce le verifiche del notaio.",
    }
