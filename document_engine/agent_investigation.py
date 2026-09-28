"""Build an explainable investigation plan from existing findings.

Hypotheses are labelled possibilities, never facts. Readiness concerns the next
review action, not permission to sell, rent or close a professional check.
"""
from collections import defaultdict
from datetime import date
import json

from core.operational_models import stable_id
from document_engine.cross_validation import _float
from document_engine.validation_coverage import finding_domain
from document_engine.validation_rules import document_date, eligible_sources
from document_engine.operation_validation import operation_key, unit_set

VERSION = "1.0"
OPEN_STATUSES = {"attention", "conflict", "invalid", "extraction_unstable"}
UNIT_KEYS = ("comune", "sezione", "foglio", "particella", "subalterno")

# Consequence, hypotheses with discriminating checks, closure evidence, owner.
GUIDANCE = {
    "technical": ("L’esito tecnico richiede di chiarire perimetro, rilievi e documenti esaminati.",
        [("Relazioni riferite a date o verifiche differenti", "Confrontare data, unità, titoli e perimetro di ciascuna verifica."),
         ("Rilievo già gestito oppure ancora aperto", "Chiedere al tecnico l’esito documentato dello specifico rilievo.")],
        ["Relazione pertinente con identificazione dell’unità e dei rilievi.", "Esito del tecnico su ciascun punto, con eventuali aggiornamenti documentali."], "Tecnico"),
    "reading": ("Una lettura incerta può alterare i confronti successivi.",
        [("Errore di lettura o estrazioni discordanti", "Aprire il passaggio originale e confrontare le letture."),
         ("Fonte incompleta o non utilizzabile", "Controllare pagine, stato di elaborazione e collegamento alla pratica.")],
        ["Valore confermato sul documento originale con pagina o citazione.", "Nuova esecuzione dei controlli interessati dalla correzione."], "Agente"),
    "identity": ("Prima di usare un confronto occorre sapere a quale unità si riferisce.",
        [("Unità principale e pertinenza confuse", "Confrontare tutti gli identificativi, senza dedurre il ruolo dalla categoria."),
         ("Variazione catastale oppure documento di altra unità", "Ricostruire la corrispondenza e le date con il tecnico.")],
        ["Associazione documentata di ciascuna fonte all’unità corretta.", "Eventuale ricostruzione tecnica della variazione degli identificativi."], "Agente e tecnico"),
    "use": ("L’uso da proporre al cliente richiede un riscontro nei documenti pertinenti.",
        [("Categoria di una pertinenza scambiata per quella dell’abitazione", "Collegare categoria e ruolo a un subalterno preciso."),
         ("Uso dichiarato differente da quello documentato", "Confrontare uso previsto, titoli e relazione tecnica della stessa unità.")],
        ["Identificazione dell’unità principale e delle pertinenze.", "Esito del tecnico su uso, titoli e stato attuale, con fonti pertinenti."], "Tecnico"),
    "authority": ("La pratica richiede di chiarire chi interviene, per quale diritto e con quali poteri.",
        [("Nominativi riferiti a passaggi o ruoli differenti", "Confrontare ruoli e cronologia della provenienza."),
         ("Comproprietà, diritto diverso o rappresentanza", "Esaminare quote, titoli ed eventuali procure pertinenti.")],
        ["Provenienza e intestazioni pertinenti all’unità.", "Conferma professionale dei soggetti, diritti, quote e poteri di firma."], "Agente e notaio"),
    "encumbrances": ("Le formalità possono incidere sulle condizioni da concordare.",
        [("Stato storico aggiornato da un’annotazione", "Collegare nota e annotazione con identificativo, unità e data."),
         ("Cancellazione soltanto richiesta o parziale", "Verificare lo stato documentato e ciò che resta da gestire.")],
        ["Note e annotazioni riferite alla medesima formalità.", "Conferma del professionista sullo stato pertinente e sulla gestione nella trattativa."], "Notaio"),
    "conditions": ("Termini ed esiti delle condizioni influenzano i passi successivi della trattativa.",
        [("Esito o proroga già documentati ma non collegati", "Cercare il richiamo alla stessa operazione e alla stessa condizione."),
         ("Condizione ancora aperta", "Richiedere la prova dell’esito e chiarire il termine con le parti.")],
        ["Identificazione della stessa operazione e clausola.", "Documento pertinente sull’esito o sulla modifica, con conferma del referente."], "Agente e parti"),
    "operation": ("Confrontare contratti diversi può creare un’incongruenza apparente.",
        [("Preliminare e atto appartengono a operazioni differenti", "Controllare richiamo contrattuale completo, date e unità."),
         ("Accordi o soggetti modificati durante la trattativa", "Esaminare modifiche sottoscritte e ragioni della variazione.")],
        ["Richiamo esplicito alla medesima operazione e oggetto completo.", "Conferma delle clausole e delle eventuali modifiche documentate."], "Agente e professionista incaricato"),
    "occupancy": ("La disponibilità da comunicare al cliente deve riflettere la situazione attuale.",
        [("Contratto storico con rilascio successivo", "Cercare risoluzione e riconsegna pertinenti al contratto."),
         ("Locazione in corso o rinnovata", "Confermare occupazione, registrazione e aggiornamenti con il proprietario.")],
        ["Stato di occupazione confermato e contratto pertinente.", "Eventuali atti di risoluzione, proroga o verbale di riconsegna."], "Agente e proprietario"),
    "surface": ("Misure non confrontabili possono alterare annuncio e valutazione.",
        [("Criteri di misura diversi", "Distinguere superficie utile, catastale e commerciale."),
         ("Pertinenze o unità incluse diversamente", "Ricostruire il perimetro delle superfici con il tecnico.")],
        ["Identificazione delle unità e dei criteri di misura.", "Misure riconciliate sulle fonti tecniche."], "Tecnico"),
    "economics": ("Il cliente deve conoscere l’importo riferito all’accordo e alle componenti corrette.",
        [("Importo richiesto diverso da quello concordato", "Confrontare ruolo del documento, operazione e data."),
         ("Periodo o componenti inclusi differenti", "Distinguere canone, spese, caparra e altri importi.")],
        ["Clausole economiche della stessa operazione.", "Riconciliazione delle componenti e delle eventuali modifiche."], "Agente"),
    "energy": ("Il dato energetico comunicato deve essere riferito all’attestato e all’unità pertinenti.",
        [("Attestati diversi nel tempo", "Controllare unità, identificativi e date degli attestati."),
         ("Errore di lettura o dato dell’annuncio non aggiornato", "Confrontare i passaggi originali e il dato comunicato.")],
        ["Attestato pertinente identificato e dato confermato.", "Chiarimento del certificatore quando necessario."], "Agente e certificatore"),
    "condominium": ("Spese e limitazioni vanno riferite alla specifica unità.",
        [("Morosità o spesa relativa ad altre unità", "Chiedere il riparto e la situazione contabile pertinente."),
         ("Clausola da interpretare rispetto all’uso previsto", "Esaminare il testo completo e chiedere conferma al referente.")],
        ["Regolamento, delibere e riparti pertinenti.", "Chiarimento dell’amministratore o del professionista incaricato."], "Amministratore"),
    "other": ("Il dato non è ancora chiarito dalle fonti disponibili.",
        [("Informazione incompleta o non aggiornata", "Aprire le fonti e chiedere il chiarimento al referente.")],
        ["Fonte pertinente e conferma del dato segnalato."], "Agente"),
}


def _scope_key(finding):
    scope = finding.scope or {}
    if scope.get("unit_set"):
        try:
            units = json.loads(scope["unit_set"])
            # The single-unit representation must group with ordinary findings.
            if len(units) == 1:
                return json.dumps(units[0], sort_keys=True)
            return json.dumps({"units": sorted(units, key=lambda u: json.dumps(u, sort_keys=True))}, sort_keys=True)
        except (ValueError, TypeError):
            pass
    if all(scope.get(k) for k in ("comune", "foglio", "particella", "subalterno")):
        return json.dumps({k: scope.get(k, "") for k in UNIT_KEYS}, sort_keys=True)
    return json.dumps({"sources": sorted(finding.sources)}, sort_keys=True)


def _domain(finding):
    if finding.rule_id in {"source_eligibility", "field_format"} or finding.status == "extraction_unstable":
        return "reading"
    if finding.rule_id == "unit_scope":
        return "identity"
    if finding.rule_id in {"operation_scope", "operation_comparison"}:
        return "operation"
    if finding.rule_id in {"operation_condition_evidence", "operation_condition_history"}:
        return "conditions"
    if finding.rule_id in {"technical_scope", "technical_declaration"} or finding.field.startswith("tecnica."):
        return "technical"
    return finding_domain(finding)


def build_investigation_plan(property_id, property_record, documents, findings, today=None):
    today = today or date.today()
    groups = defaultdict(list)
    for finding in findings:
        if finding.status not in OPEN_STATUSES:
            continue
        domain, scope = _domain(finding), _scope_key(finding)
        groups[(domain, scope)].append(finding)
        uncertain = any(_float(v.get("confidence")) is not None and _float(v.get("confidence")) < .4 for v in finding.values)
        if uncertain and domain != "reading":
            groups[("reading", scope)].append(finding)
    cases = []
    for (domain, scope), items in sorted(groups.items()):
        consequence, hypotheses, required, owner = GUIDANCE.get(domain, GUIDANCE["other"])
        items = sorted({f.finding_id: f for f in items}.values(), key=lambda f: f.finding_id)
        sources = sorted({s for f in items for s in f.sources})
        proof = any(f.rule_id == "operation_condition_evidence" for f in items)
        cases.append({"case_id": stable_id("investigation", property_id, domain, scope), "domain": domain,
            "scope": json.loads(scope), "priority": "high" if any(f.severity == "high" for f in items) else "medium",
            "title": "Conferma la lettura prima del confronto" if domain == "reading" else items[0].label or items[0].field,
            "why_it_matters": consequence, "assigned_role": owner, "sources": sources,
            "finding_ids": [f.finding_id for f in items], "evidence_ids": sorted({e for f in items for e in f.evidence_ids}),
            "observations": [{"finding_id": f.finding_id, "detail": f.detail, "values": f.values} for f in items],
            "possible_explanations": [{"hypothesis": h, "how_to_check": check, "confirmed": False} for h, check in hypotheses],
            "closure_requirements": required, "automatic_closure": False,
            "status": "review_available_evidence" if proof else "verify_reading" if domain == "reading" else "investigate",
            "next_step": "Apri la prova sull’esito già presente e fai confermare la clausola al referente." if proof else required[0],
            "blocked_by": []})
    tier = {"reading": 0, "identity": 1, "operation": 2}
    for case in cases:
        for prerequisite in cases:
            if tier.get(prerequisite["domain"], 3) >= tier.get(case["domain"], 3):
                continue
            if set(case["sources"]) & set(prerequisite["sources"]):
                case["blocked_by"].append(prerequisite["case_id"])
        case["blocked_by"].sort()
    domain_order = {name: i for i, name in enumerate(("reading", "identity", "operation", "authority", "use", "technical", "encumbrances", "conditions", "occupancy", "energy", "surface", "economics", "condominium", "other"))}
    cases.sort(key=lambda c: (bool(c["blocked_by"]), tier.get(c["domain"], 3), c["priority"] != "high", domain_order.get(c["domain"], 99), c["case_id"]))
    _, docs, _ = eligible_sources(property_id, [], documents)
    timeline = [{"source_key": f"doc:{d['id']}", "document_type": d.get("document_type"),
                 "document_date": document_date(d), "operation": operation_key(d),
                 "units": [json.loads(u) for u in unit_set(d)]} for d in docs]
    timeline.sort(key=lambda x: (x["document_date"] is None, x["document_date"] or "", x["source_key"]))
    references = {tuple(row["operation"]) for row in timeline if row["operation"]}
    kinds = {d.get("document_type") for d in docs}
    context_questions = []
    if len(references) > 1:
        context_questions.append("Quale operazione è attualmente in corso? Sono presenti richiami a operazioni distinte.")
    elif {"preliminare_compravendita", "atto_compravendita"} <= kinds and any(not row["operation"] for row in timeline if row["document_type"] in {"preliminare_compravendita", "atto_compravendita"}):
        context_questions.append("A quale operazione si riferiscono preliminare e atto? Recupera il richiamo contrattuale esplicito prima di collegarli.")
    return {"version": VERSION, "as_of": today.isoformat(), "cases": cases, "timeline": timeline,
            "next_case_id": next((c["case_id"] for c in cases if not c["blocked_by"]), None),
            "context_questions": context_questions,
            "note": "Le spiegazioni sono ipotesi da verificare. Le dipendenze ordinano il lavoro; nessun caso viene chiuso automaticamente e nessun esito autorizza la trattativa."}
