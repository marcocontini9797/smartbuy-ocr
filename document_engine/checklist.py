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

from dataclasses import asdict, dataclass, field, replace
from datetime import date
from typing import Any

from core.operational_models import CrossValidationFinding
from fascicolo import Fascicolo, aggiungi_al_fascicolo
from document_engine.validation_rules import category_findings, effective_documents, eligible_sources
from document_engine.typology import Typology, contract_of, typology_of, TYPOLOGIES
from document_engine.workflow_context import applicability, document_condition, QUESTIONS
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
    typologies: frozenset[str] | None = None  # None = every typology of the bucket's asset class


_MORTGAGE_WHY = ("Mostra ipoteche, pignoramenti, provenienza e altre formalità sull'immobile. Da fare prima della proposta: "
                 "circa 20–35 € di tributi (Sister o servizio online con SPID), il notaio la rifà solo prima del rogito.")

# Residential sale. Operational checklist, not a statement of legal duties:
# the notary decides what is needed for the deed.
SALE_CHECKLIST: tuple[ChecklistSpec, ...] = (
    ChecklistSpec("visura_catastale", "Visura catastale", "Identifica l'immobile e chi ne risulta intestatario.",
                  "Venditore o tecnico", "required"),
    ChecklistSpec("planimetria", "Planimetria catastale", "Serve a verificare la conformità catastale, da dichiarare nell'atto.",
                  "Venditore", "required", ("conformita_catastale",)),
    ChecklistSpec("ape", "APE – Attestato di prestazione energetica", "È obbligatorio e va allegato all'atto di vendita.",
                  "Venditore", "required", ("ape",)),
    ChecklistSpec("visura_ipotecaria", "Ispezione ipotecaria aggiornata", _MORTGAGE_WHY,
                  "Agente (Sister o SPID) o notaio", "required", ("formalita_pregiudizievoli",)),
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

_NEGOZIO = frozenset({"negozio"})
_UFFICIO = frozenset({"ufficio"})
_CAPANNONE = frozenset({"capannone", "laboratorio"})
_MAGAZZINO = frozenset({"magazzino"})
_CENTRO_COMMERCIALE = frozenset({"centro_commerciale"})
# Typologies where a SCIA/licenza commerciale (retail or public-facing activity)
# and a CPI (larger or industrial spaces) are realistically expected.
_SCIA_TYPOLOGIES = frozenset(k for k, t in TYPOLOGIES.items() if t.asset == "commerciale")
_CPI_TYPOLOGIES = frozenset(TYPOLOGIES)

# Commercial unit: agibilità and systems are needed to open a business, the
# building titles must show the commercial use, and a lease in place brings
# registration and the tenant's pre-emption right. The expected cadastral
# category (and whether a SCIA/CPI applies) differs by exact typology, so
# those items are typology-scoped instead of shared across all five.
COMMERCIAL_CHECKLIST: tuple[ChecklistSpec, ...] = (
    ChecklistSpec("visura_catastale", "Visura catastale", "Identifica il locale, l'intestatario e la categoria catastale attesa: C/1 (negozi) o C/3 (laboratori).",
                  "Venditore o tecnico", "required", typologies=_NEGOZIO),
    ChecklistSpec("visura_catastale", "Visura catastale", "Identifica il locale, l'intestatario e la categoria catastale attesa: A/10 (uffici) o D/5 (istituti di credito/assicurazione).",
                  "Venditore o tecnico", "required", typologies=_UFFICIO),
    ChecklistSpec("visura_catastale", "Visura catastale", "Identifica il locale, l'intestatario e la categoria catastale attesa: D/1 o D/7 (capannoni industriali/artigianali).",
                  "Venditore o tecnico", "required", typologies=_CAPANNONE),
    ChecklistSpec("visura_catastale", "Visura catastale", "Identifica il locale, l'intestatario e la categoria catastale attesa: C/2 (magazzini/depositi).",
                  "Venditore o tecnico", "required", typologies=_MAGAZZINO),
    ChecklistSpec("visura_catastale", "Visura catastale", "Identifica il locale, l'intestatario e la categoria catastale attesa: D/8 (fabbricati commerciali).",
                  "Venditore o tecnico", "required", typologies=_CENTRO_COMMERCIALE),
    ChecklistSpec("planimetria", "Planimetria catastale", "Serve a verificare la conformità catastale, da dichiarare nell'atto.",
                  "Venditore", "required", ("conformita_catastale",)),
    ChecklistSpec("ape", "APE – Attestato di prestazione energetica", "Obbligatorio anche per i locali commerciali, va allegato all'atto.",
                  "Venditore", "required", ("ape",)),
    ChecklistSpec("visura_ipotecaria", "Ispezione ipotecaria aggiornata", _MORTGAGE_WHY,
                  "Agente (Sister o SPID) o notaio", "required", ("formalita_pregiudizievoli",)),
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
    ChecklistSpec("scia_licenza_commerciale", "SCIA o licenza per l'attività commerciale", "Conferma che l'attività effettivamente svolta nel locale è autorizzata.",
                  "Venditore", "recommended", typologies=_SCIA_TYPOLOGIES),
    ChecklistSpec("certificato_prevenzione_incendi", "Certificato di prevenzione incendi (CPI/SCIA antincendio)", "Necessario se l'attività o la superficie superano le soglie del DPR 151/2011.",
                  "Venditore", "recommended", typologies=_CPI_TYPOLOGIES),
    ChecklistSpec("regolamento_condominio", "Regolamento di condominio", "Può vietare o limitare alcune attività commerciali nel locale.",
                  "Amministratore", "condominium"),
    ChecklistSpec("verbale_assemblea_condominio", "Ultimi verbali di assemblea", "Lavori deliberati, spese straordinarie e morosità da chiarire prima del rogito.",
                  "Amministratore", "condominium", ("condominio",)),
)

# Garage or parking space for sale: no APE (exempt), no agibilità of its own.
BOX_CHECKLIST: tuple[ChecklistSpec, ...] = (
    ChecklistSpec("visura_catastale", "Visura catastale", "Identifica il box, l'intestatario e la categoria (C/6 o C/7).",
                  "Venditore o tecnico", "required"),
    ChecklistSpec("planimetria", "Planimetria catastale", "Serve a verificare la conformità catastale, da dichiarare nell'atto.",
                  "Venditore", "required", ("conformita_catastale",)),
    ChecklistSpec("visura_ipotecaria", "Ispezione ipotecaria aggiornata", _MORTGAGE_WHY,
                  "Agente (Sister o SPID) o notaio", "required", ("formalita_pregiudizievoli",)),
    ChecklistSpec("atto_di_provenienza", "Atto di provenienza", "Dimostra come il venditore è diventato proprietario; "
                  "verifica anche vincoli di pertinenza (box legati a un appartamento, legge Tognoli).",
                  "Venditore", "required", ("provenienza",)),
    ChecklistSpec("titolo_edilizio", "Titoli edilizi", "Dimostrano che il box è regolare dal punto di vista urbanistico.",
                  "Venditore o tecnico", "recommended", ("conformita_urbanistica", "vincoli")),
    ChecklistSpec("regolamento_condominio", "Regolamento di condominio", "Regole d'uso dell'autorimessa e delle parti comuni.",
                  "Amministratore", "condominium"),
    ChecklistSpec("verbale_assemblea_condominio", "Ultimi verbali di assemblea", "Lavori deliberati e spese da chiarire prima del rogito.",
                  "Amministratore", "condominium", ("condominio",)),
)

# Lease of a home: the owner must deliver the APE and prove who can let the flat.
LEASE_CHECKLIST: tuple[ChecklistSpec, ...] = (
    ChecklistSpec("visura_catastale", "Visura catastale", "Identifica l'immobile e verifica che chi affitta ne sia proprietario o abbia titolo.",
                  "Proprietario o tecnico", "required"),
    ChecklistSpec("ape", "APE – Attestato di prestazione energetica", "Obbligatorio: la classe energetica va nell'annuncio e il contratto "
                  "deve dare atto che l'inquilino ha ricevuto l'APE.", "Proprietario", "required", ("ape",)),
    ChecklistSpec("planimetria", "Planimetria catastale", "Descrive i locali consegnati e va spesso allegata al contratto.",
                  "Proprietario", "recommended", ("conformita_catastale",)),
    ChecklistSpec("dichiarazione_conformita_impianti", "Conformità degli impianti", "Impianti a norma: sicurezza dell'inquilino e responsabilità del proprietario.",
                  "Proprietario", "recommended", ("conformita_impianti",)),
    ChecklistSpec("certificato_agibilita", "Agibilità", "Attesta che l'immobile è utilizzabile per abitarci.",
                  "Proprietario", "recommended", ("agibilita",)),
    ChecklistSpec("visura_ipotecaria", "Ispezione ipotecaria", "Un pignoramento trascritto prima del contratto può renderlo inopponibile "
                  "all'acquirente all'asta: l'inquilino rischia di dover lasciare l'immobile.", "Agente (Sister o SPID)", "recommended",
                  ("formalita_pregiudizievoli",)),
    ChecklistSpec("regolamento_condominio", "Regolamento di condominio", "Divieti e regole (animali, uso delle parti comuni, affitti brevi) "
                  "che l'inquilino deve rispettare.", "Amministratore", "condominium"),
)

# Lease of a commercial unit: the use must allow the tenant's business.
COMMERCIAL_LEASE_CHECKLIST: tuple[ChecklistSpec, ...] = (
    ChecklistSpec("visura_catastale", "Visura catastale", "Identifica il locale, chi lo affitta e la categoria catastale attesa: C/1 (negozi) o C/3 (laboratori).",
                  "Proprietario o tecnico", "required", typologies=_NEGOZIO),
    ChecklistSpec("visura_catastale", "Visura catastale", "Identifica il locale, chi lo affitta e la categoria catastale attesa: A/10 (uffici) o D/5 (istituti di credito/assicurazione).",
                  "Proprietario o tecnico", "required", typologies=_UFFICIO),
    ChecklistSpec("visura_catastale", "Visura catastale", "Identifica il locale, chi lo affitta e la categoria catastale attesa: D/1 o D/7 (capannoni industriali/artigianali).",
                  "Proprietario o tecnico", "required", typologies=_CAPANNONE),
    ChecklistSpec("visura_catastale", "Visura catastale", "Identifica il locale, chi lo affitta e la categoria catastale attesa: C/2 (magazzini/depositi).",
                  "Proprietario o tecnico", "required", typologies=_MAGAZZINO),
    ChecklistSpec("visura_catastale", "Visura catastale", "Identifica il locale, chi lo affitta e la categoria catastale attesa: D/8 (fabbricati commerciali).",
                  "Proprietario o tecnico", "required", typologies=_CENTRO_COMMERCIALE),
    ChecklistSpec("ape", "APE – Attestato di prestazione energetica", "Obbligatorio anche per i locali commerciali in affitto.",
                  "Proprietario", "required", ("ape",)),
    ChecklistSpec("titolo_edilizio", "Titoli edilizi e destinazione d'uso", "L'attività dell'inquilino deve essere compatibile con la destinazione d'uso legittima.",
                  "Proprietario o tecnico", "required", ("conformita_urbanistica", "vincoli")),
    ChecklistSpec("certificato_agibilita", "Agibilità", "Senza agibilità l'inquilino può non ottenere le autorizzazioni per l'attività.",
                  "Proprietario", "required", ("agibilita",)),
    ChecklistSpec("dichiarazione_conformita_impianti", "Conformità degli impianti", "Necessaria per l'uso aperto al pubblico e per le licenze.",
                  "Proprietario", "required", ("conformita_impianti",)),
    ChecklistSpec("planimetria", "Planimetria catastale", "Descrive i locali consegnati.", "Proprietario", "recommended", ("conformita_catastale",)),
    ChecklistSpec("visura_ipotecaria", "Ispezione ipotecaria", "Un pignoramento anteriore al contratto può renderlo inopponibile all'acquirente all'asta.",
                  "Agente (Sister o SPID)", "recommended", ("formalita_pregiudizievoli",)),
    ChecklistSpec("scia_licenza_commerciale", "SCIA o licenza per l'attività commerciale", "Il conduttore deve poter ottenere o subentrare in un titolo valido per l'attività prevista.",
                  "Proprietario o conduttore", "recommended", typologies=_SCIA_TYPOLOGIES),
    ChecklistSpec("certificato_prevenzione_incendi", "Certificato di prevenzione incendi (CPI/SCIA antincendio)", "Necessario se l'attività o la superficie superano le soglie del DPR 151/2011.",
                  "Proprietario", "recommended", typologies=_CPI_TYPOLOGIES),
    ChecklistSpec("regolamento_condominio", "Regolamento di condominio", "Può vietare o limitare alcune attività commerciali nel locale.",
                  "Amministratore", "condominium"),
)


def specs_for(property_record: dict[str, Any]) -> tuple[ChecklistSpec, ...]:
    typology, contract = typology_of(property_record), contract_of(property_record)
    if contract == "affitto" and typology.key == "box":
        return tuple(s for s in BOX_CHECKLIST if s.key not in {"visura_ipotecaria", "titolo_edilizio"})
    if contract == "affitto":
        return COMMERCIAL_LEASE_CHECKLIST if typology.asset == "commerciale" else LEASE_CHECKLIST
    if typology.key == "box":
        return BOX_CHECKLIST
    return COMMERCIAL_CHECKLIST if typology.asset == "commerciale" else SALE_CHECKLIST

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
    category = "categoria_catastale" if finding.rule_id == "category_use" else "proprietari" if finding.rule_id in {"party_roles", "ownership_rights"} else finding.field
    return {"source": "verifica", "category": category,
            "level": level, "severity": finding.severity, "title": finding.label or finding.field,
            "detail": finding.detail, "action": finding.recommended_action, "reference": None,
            "finding_id": finding.finding_id, "rule_id": finding.rule_id, "sources": finding.sources,
            "evidence_ids": finding.evidence_ids, "scope": finding.scope}


def build_checklist(
    *,
    property_record: dict[str, Any],
    documents: list[dict[str, Any]],
    findings: list[CrossValidationFinding],
    facts: list[dict[str, Any]] | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    facts, documents, eligibility = eligible_sources(property_record["id"], facts or [], documents)
    findings = list(findings)
    fallback = eligibility + category_findings(property_record["id"], property_record, effective_documents(documents, facts))
    present = {f.finding_id for f in findings}
    findings.extend(f for f in fallback if f.finding_id not in present)
    is_condominium = property_record.get("is_condominio")
    typology, contract = typology_of(property_record), contract_of(property_record)
    specs = tuple(s for s in specs_for(property_record) if s.typologies is None or typology.key in s.typologies)
    if not any(s.key == "certificato_prevenzione_incendi" for s in specs):
        specs += (ChecklistSpec("certificato_prevenzione_incendi", "Documentazione antincendio", "Verificare l’assoggettamento in base alle caratteristiche e all’uso.", "Proprietario o tecnico", "recommended"),)
    conditions = applicability(property_record)
    conditional = {}
    for spec in specs:
        condition = document_condition(spec.key, typology.asset == "commerciale")
        if condition:
            conditional[spec.key] = condition
    specs = tuple(replace(s, requirement="conditional") if s.key in conditional and conditions[conditional[s.key]] is None else s for s in specs)
    items: dict[str, ChecklistItem] = {}
    for spec in specs:
        applicable = spec.requirement != "condominium" or is_condominium is not False
        if spec.key in conditional and conditions[conditional[spec.key]] is False:
            applicable = False
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
        if item.requirement == "conditional" and not item.documents:
            item.status = "to_check"
            item.action = QUESTIONS[conditional[item.key]]
        elif not item.documents:
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
    required = [i for i in items.values() if i.requirement == "required" and i.applicable]
    required_present = sum(1 for i in required if i.documents)
    problems = [i for i in items.values() if i.status == "problem" and i.applicable] + [g for g in general if g["level"] == "problem"]
    to_check = [i for i in items.values() if i.status == "to_check" and i.applicable] + [g for g in general if g["level"] == "to_check"]
    missing_required = [i for i in required if not i.documents]

    if problems:
        verdict, tone = "Ci sono problemi da risolvere prima della trattativa", "problem"
    elif missing_required:
        verdict, tone = f"Documentazione incompleta: mancano {len(missing_required)} documenti obbligatori", "missing"
    elif to_check:
        verdict, tone = "Quasi pronto: alcuni punti da ricontrollare", "to_check"
    else:
        verdict, tone = "Documenti presenti: nessuna criticità nei controlli disponibili", "verified"

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
        "typology": typology.key, "contract": contract,
        "note": (f"Checklist operativa per l'affitto di {typology.label.lower()}: non sostituisce la verifica del contratto."
                 if contract == "affitto" else
                 f"Checklist operativa per la compravendita di {typology.label.lower()}: non sostituisce le verifiche del notaio."),
    }
