"""Describe available evidence without turning 'no findings' into an all-clear.

This is an operational coverage map, not a probability, compliance percentage or
exhaustive catalogue of real-estate risks. Missing inputs are explicit questions.
"""
from collections import Counter
import json

from core.operational_models import stable_id
from document_engine.cross_validation import _unwrap
from document_engine.validation_rules import VERSION, effective_documents, eligible_sources, unit_records


# Each tuple is one required input group; aliases within a group are alternatives.
DOMAINS = (
    ("identity", "Unità e pertinenze", (("riferimento", "riferimenti_catastali", "riferimento_catastale", "cadastral"),),
     "Associa Comune, sezione, foglio, particella e subalterno dell’unità principale e delle pertinenze.", "Agente e tecnico"),
    ("authority", "Soggetti, quote e provenienza", (("intestatari",), ("titolarita",), ("parte_acquirente", "avente_causa")),
     "Raccogli provenienza e intestazioni aggiornate, con soggetti, diritti, quote e poteri di firma.", "Agente e notaio"),
    ("use", "Uso previsto e stato tecnico", (("destinazione_uso_legittima", "destinazione_uso"), ("conformita_urbanistica",), ("conformita_catastale",)),
     "Chiedi al tecnico il confronto tra uso previsto, titoli, planimetria e stato attuale.", "Tecnico"),
    ("encumbrances", "Formalità e vincoli", (("formalita", "formalita_ancora_attiva"),),
     "Acquisisci l’ispezione pertinente e collega le note e le eventuali annotazioni.", "Notaio o professionista incaricato"),
    ("energy", "Dati energetici", (("classe_energetica", "energy_class"), ("data_scadenza",)),
     "Associa l’APE all’unità e verifica classe, date e documento pertinente.", "Proprietario e certificatore"),
    ("surface", "Superfici confrontabili", (("superficie_catastale_mq",), ("superficie_utile_mq", "superficie_commerciale_mq", "superficie_commerciale_considerata_mq", "superficie_dichiarata_mq")),
     "Recupera superfici e criteri di misura distinguendo unità principale e pertinenze.", "Agente e tecnico"),
    ("economics", "Importi e condizioni economiche", (("prezzo_eur", "canone_mensile_eur"),),
     "Distingui importi richiesti e concordati, stessa operazione, periodo e componenti incluse.", "Agente"),
    ("occupancy", "Occupazione e disponibilità", (("locatore",), ("conduttore",), ("registrato",)),
     "Conferma occupazione attuale, contratto, registrazione e documenti su rinnovo o rilascio.", "Proprietario"),
    ("conditions", "Condizioni della trattativa", (("condizioni_dettaglio", "condizioni_sospensive"), ("termine_rogito",)),
     "Individua l’operazione corrente, i termini e la prova dell’esito di ogni condizione.", "Agente e parti"),
    ("condominium", "Situazione condominiale", (("tipo_regolamento", "limitazioni_uso"), ("delibere", "morosita_menzionata")),
     "Raccogli regolamento, verbali e situazione contabile riferita alla specifica unità.", "Amministratore"),
)


def finding_domain(finding):
    rule, field = finding.rule_id, finding.field
    if rule == "party_roles" or rule == "ownership_rights" or field in {"proprietari", "codici_fiscali", "quota_proprieta"}:
        return "authority"
    if rule in {"category_use", "declared_use", "technical_declaration", "technical_scope"} or field.startswith("tecnica."):
        return "use"
    if rule == "encumbrances": return "encumbrances"
    if rule == "occupancy": return "occupancy"
    if rule == "contract_conditions": return "conditions"
    if rule in {"operation_condition_evidence", "operation_condition_history"}: return "conditions"
    if rule in {"operation_scope", "operation_comparison"}: return "conditions"
    if rule == "condominium": return "condominium"
    if field.startswith("catasto.") or field == "indirizzo": return "identity"
    if field.startswith("ape.") or field in {"classe_energetica", "epgl"}: return "energy"
    if field.startswith("superficie"): return "surface"
    if field.startswith("economia.") or field in {"prezzo_eur", "canone_mensile_eur"}: return "economics"
    return "other"


def build_validation_coverage(property_id, property_record, documents, findings, facts=()):
    facts, docs, _ = eligible_sources(property_id, list(facts), documents)
    docs = effective_documents(docs, facts)
    prop = property_record or {}
    context = prop.get("workflow_context") or {}
    known_units = {json.dumps(u["identity"], sort_keys=True): u["identity"]
                   for d in docs for u in unit_records(d) if u["complete"]}
    rows = []
    for key, label, groups, step, owner in DOMAINS:
        # A lease expiry cannot satisfy the APE input group.
        relevant = [d for d in docs if key != "energy" or d.get("document_type") == "ape"]
        available = {name for d in relevant for name, raw in d["extracted_fields"].items()
                     if _unwrap(raw) is not None and _unwrap(raw) != "" and _unwrap(raw) != [] and _unwrap(raw) != {}}
        missing = [" / ".join(group) for group in groups if not available.intersection(group)]
        if key == "identity" and not any(u["complete"] for d in relevant for u in unit_records(d)):
            missing = ["identificativo catastale completo dell’unità"]
        if key == "occupancy" and context.get("occupancy", "unknown") == "unknown":
            missing.insert(0, "stato di occupazione attuale")
        issues = [f for f in findings if finding_domain(f) == key]
        flagged = [f for f in issues if f.status in {"attention", "conflict", "invalid", "extraction_unstable"}]
        sources = sorted({f"doc:{d['id']}" for d in relevant
                          if any(name in d["extracted_fields"] and _unwrap(d["extracted_fields"][name]) not in (None, "", [], {})
                                 for group in groups for name in group)})
        status = "needs_review" if flagged else "needs_input" if missing else "available_for_review"
        if not flagged and not missing and any(f.status in {"consistent", "compatible"} for f in issues):
            status = "compared_in_part"
        # Do not complete one unit's dossier with another unit's fields. Global
        # values on a multiunit deed remain unassigned until their scope is known.
        scoped = []
        unassigned = set()
        for encoded, identity in sorted(known_units.items()):
            unit_docs = []
            for d in relevant:
                refs = unit_records(d)
                identities = {json.dumps(u["identity"], sort_keys=True) for u in refs if u["complete"]}
                if len(identities) == 1 and encoded in identities and all(u["complete"] for u in refs):
                    unit_docs.append(d)
                elif encoded in identities and key == "identity":
                    unit_docs.append({**d, "extracted_fields": {"riferimento": identity}})
                elif f"doc:{d['id']}" in sources and (not refs or len(identities) != 1 or any(not u["complete"] for u in refs)):
                    unassigned.add(f"doc:{d['id']}")
            present = {name for d in unit_docs for name, raw in d["extracted_fields"].items()
                       if _unwrap(raw) not in (None, "", [], {})}
            gaps = [" / ".join(group) for group in groups if not present.intersection(group)]
            scoped.append({"scope": identity, "sources": sorted({f"doc:{d['id']}" for d in unit_docs
                           if any(set(group) & present & set(d["extracted_fields"]) for group in groups)}),
                           "missing_inputs": gaps, "status": "needs_input" if gaps else "available_for_review"})
        if len(known_units) > 1 and any(row["missing_inputs"] for row in scoped):
            if not flagged:
                status = "needs_input"
            missing = sorted(set(missing) | {"dati da associare e completare per ciascuna unità"})
        if key == "condominium" and prop.get("is_condominio") is False and not sources:
            status, missing = "not_applicable_declared", []
        # Even an unoccupied property needs a confirmed current occupancy; the
        # lease-only documents are unnecessary when no contrary source exists.
        if key == "occupancy" and context.get("occupancy") in {"vacant", "free", "libero"} and not sources and not flagged:
            status, missing = "declared_only", []
        rows.append({"id": stable_id("coverage", property_id, key), "domain": key, "label": label,
                     "status": status, "missing_inputs": missing, "sources": sources,
                     "units": scoped, "unassigned_sources": sorted(unassigned),
                     "finding_ids": sorted(f.finding_id for f in issues), "next_step": step,
                     "assigned_role": owner})
    return {"version": VERSION, "domains": rows, "counts": dict(Counter(row["status"] for row in rows)),
            "note": "Copertura dei controlli implementati sui dati disponibili; non è una certificazione né una percentuale di rischi esclusi. I confronti positivi riguardano solo i campi indicati."}
