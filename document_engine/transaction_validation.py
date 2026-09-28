"""Evidence-led checks of parties, rights and open transaction conditions.

No inferred legal deadlines, automatic clearance or comparison of unnamed units.
Structured entries are optional and can be stored in the existing extracted_fields.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
import json

from core.operational_models import stable_id
from document_engine.cross_validation import (
    SPECS, _claim, _compare_field, _unwrap, norm_boolean, norm_text, norm_people,
    parse_date, parse_number, parse_quota,
)
from document_engine.validation_rules import (
    VERSION, annotate_claims, document_date, emit, unit_records, value_ref,
)

RULES = {
    "party_roles": "Soggetti distinti per ruolo, unità e data del documento",
    "ownership_rights": "Quote confrontate separatamente per diritto e unità",
    "encumbrances": "Formalità identificate e stato documentato, senza cancellazioni presunte",
    "occupancy": "Disponibilità dichiarata e contratto di locazione",
    "contract_conditions": "Condizioni sospensive e termini espliciti della trattativa",
    "condominium": "Limitazioni, morosità menzionate e spese da chiarire",
    "technical_scope": "Difformità, stato dei titoli e limiti della verifica tecnica",
}


def _fields(doc):
    return doc.get("extracted_fields") or {}


def _record_key(record):
    return json.dumps(record, sort_keys=True, ensure_ascii=False, default=str)


def _scope(doc, record=None):
    reference = (record or {}).get("riferimento")
    units = unit_records({"extracted_fields": {"riferimento": reference}}) if reference else unit_records(doc)
    identities = {json.dumps(u["identity"], sort_keys=True) for u in units if u["complete"]}
    if len(identities) == 1 and all(u["complete"] for u in units):
        return json.loads(next(iter(identities)))
    return None


def _records(doc, key):
    raw = _fields(doc).get(key)
    records = _unwrap(raw)
    if not isinstance(records, list):
        return []
    parent = raw if isinstance(raw, dict) else {}
    return [(i, {**{k: v for k, v in parent.items() if k not in {"value", "valore"}}, **record})
            for i, record in enumerate(records) if isinstance(record, dict)]


def _ref(doc, path, record, value=None):
    return value_ref(doc, path, {**record, "value": record if value is None else value})


def _emit(property_id, doc, rule, field, title, paths, detail, action, *, scope=None, status="attention"):
    return emit(property_id, rule, field, title, [doc],
                [value_ref(doc, path, _fields(doc).get(path)) for path in paths],
                detail, action, status=status, scope=scope or _scope(doc))


def party_findings(property_id, documents, today):
    """A former seller and a current landlord are not interchangeable with an owner.

    Compare named parties only on a fully identified single unit. A match means
    concordant names, not authority to dispose of the property.
    """
    owners, participants = [], []
    for doc in documents:
        fields, kind = _fields(doc), doc.get("document_type")
        if kind == "visura_catastale" and fields.get("intestatari"):
            owners.append((doc, "intestatari"))
        key = {"preliminare_compravendita": "promittente_venditore",
               "contratto_locazione": "locatore", "atto_compravendita": "parte_acquirente",
               "atto_di_provenienza": "avente_causa"}.get(kind)
        if key and _unwrap(fields.get(key)):
            participants.append((doc, key))
    findings = []
    for doc, key in participants:
        scope = _scope(doc)
        matching = [(other, field) for other, field in owners if scope and _scope(other) == scope]
        if not matching:
            findings.append(_emit(property_id, doc, "party_roles", "titolarita.ambito", "Collega i soggetti all’unità della pratica", [key],
                "Manca una visura con la stessa unità completamente identificata per confrontare questi nominativi.",
                "Associa Comune, sezione, foglio, particella e subalterno; acquisisci la fonte pertinente e chiarisci i ruoli."))
            continue
        for other, owner_key in matching:
            values = [value_ref(d, k, _fields(d)[k]) for d, k in ((doc, key), (other, owner_key))]
            claims = [_claim("proprietari", v["value"], source_key=v["source_key"], source_label=v["source"],
                             confidence=v["confidence"], source_path=v["source_path"], page=v["page"],
                             source_text=v["source_text"], fact_id=v["fact_id"], evidence_ids=v["evidence_ids"])
                      for v in values]
            claims = annotate_claims([c for c in claims if c], documents)
            if len(claims) != 2:
                continue
            results = _compare_field(property_id, SPECS["proprietari"], claims)
            acquisition = key in {"parte_acquirente", "avente_causa"}
            a, b = parse_date(document_date(doc)), parse_date(document_date(other))
            ordered = a is not None and b is not None and a <= b <= today
            for item in results:
                item.rule_id, item.rule_version = "party_roles", VERSION
                item.field = "titolarita." + key
                item.label = "Confronto nominativi per ruolo: " + key.replace("_", " ")
                item.scope = scope
                item.finding_id = stable_id("party-roles", property_id, key, json.dumps(scope, sort_keys=True), *sorted(item.sources))
                # A partial name or missing chronology cannot confirm identity.
                if item.status in {"conflict", "compatible"} or (acquisition and not ordered):
                    item.status = "attention"
                    item.canonical_value = None
                item.detail += " I ruoli restano distinti; la concordanza dei nomi non prova proprietà o poteri di firma."
                if acquisition and not ordered:
                    item.detail += " La data della visura non è confermata come successiva all’acquisto e non futura."
                item.recommended_action = "Ricostruisci provenienza, date, quote, eventuali rappresentanti e poteri di firma con il professionista incaricato."
                findings.append(item)
    return findings


def rights_findings(property_id, documents):
    findings = []
    for doc in documents:
        groups = defaultdict(list)
        for index, record in _records(doc, "titolarita"):
            right = norm_text(record.get("diritto")) if record.get("diritto") else ""
            scope = _scope(doc, record)
            raw_quota = _unwrap(record.get("quota"))
            quota = parse_quota(raw_quota)
            value = _ref(doc, f"titolarita[{index}]", record)
            key = stable_id("right", record.get("soggetto"), right, json.dumps(scope, sort_keys=True))
            if not scope or not right or not record.get("soggetto") or quota is None or not 0 < quota <= 1:
                findings.append(emit(property_id, "ownership_rights", "titolarita.quota." + key, "Chiarisci soggetto, diritto e quota", [doc], [value],
                    "La quota non è interpretabile oppure manca l’associazione a un soggetto, a un diritto o a una singola unità.",
                    "Controlla il testo originale senza sommare proprietà, nuda proprietà e usufrutto.", scope=scope))
                continue
            groups[(json.dumps(scope, sort_keys=True), right)].append((record, quota, value))
        for (scope_key, right), entries in groups.items():
            # Exact duplicates are one observation; different readings of one person
            # need review instead of being added together.
            by_person = defaultdict(list)
            for record, quota, value in entries:
                by_person[norm_people(record["soggetto"])].append((quota, value))
            unstable = any(len({q for q, _ in values}) > 1 for values in by_person.values())
            total = sum(values[0][0] for values in by_person.values())
            complete = norm_boolean(_unwrap(_fields(doc).get("elenco_titolari_completo"))) is True
            if unstable or total > 1.000001 or (complete and total < .999999):
                findings.append(emit(property_id, "ownership_rights", "titolarita.totale." + right, "Riconcilia le quote dello stesso diritto", [doc],
                    [v for _, _, v in entries], "Le quote dello stesso diritto e della stessa unità presentano letture diverse o un totale da riconciliare. Un elenco parziale non deve necessariamente totalizzare 100%.",
                    "Verifica l’elenco completo e le quote di ciascun soggetto; non unire diritti differenti.", scope=json.loads(scope_key)))
    return findings


def encumbrance_findings(property_id, documents):
    findings, grouped = [], defaultdict(list)
    for doc in documents:
        records = _records(doc, "formalita")
        fields = _fields(doc)
        summary_state = norm_boolean(_unwrap(fields.get("formalita_ancora_attiva")))
        states = {norm_text(record.get("stato")) for _, record in records}
        if records and ((summary_state is True and states == {"cancellata"}) or (summary_state is False and "attiva" in states)):
            findings.append(_emit(property_id, doc, "encumbrances", "vincoli.riepilogo", "Riepilogo e dettaglio delle formalità discordanti",
                ["formalita_ancora_attiva", "formalita"],
                "Lo stato sintetico non coincide con il dettaglio delle note estratte dallo stesso documento.",
                "Rileggi le note e correggi il riepilogo; non scegliere automaticamente il risultato più favorevole."))
        if not records and doc.get("document_type") == "visura_ipotecaria" and norm_boolean(_unwrap(fields.get("formalita_ancora_attiva"))) is True:
            findings.append(_emit(property_id, doc, "encumbrances", "vincoli.formalita_attiva", "Formalità indicata come attiva", ["tipo_formalita", "formalita_ancora_attiva"],
                "La fonte riporta una formalità attiva. L’importo di iscrizione non equivale al debito residuo.",
                "Recupera nota, aggiornamento dell’ispezione e documentazione sulla gestione o cancellazione con il notaio."))
        for index, record in records:
            scope, identifier = _scope(doc, record), record.get("identificativo")
            state = norm_text(record.get("stato"))
            value = _ref(doc, f"formalita[{index}]", record)
            key = stable_id("formality", identifier or _record_key(record), json.dumps(scope, sort_keys=True))
            if not scope or not identifier or state not in {"attiva", "cancellata"}:
                findings.append(emit(property_id, "encumbrances", "vincoli.ambito." + key, "Completa la verifica della formalità", [doc], [value],
                    "Identificativo, unità o stato della formalità non sono sufficienti per collegare iscrizione e annotazioni. Una cancellazione parziale o richiesta non è una cancellazione completa.",
                    "Collega la nota e le annotazioni esatte, con relativo stato e data.", scope=scope))
            if state == "attiva":
                findings.append(emit(property_id, "encumbrances", "vincoli.attiva." + key, "Formalità da gestire nella trattativa", [doc], [value],
                    "Una fonte riporta questa formalità come attiva; una semplice promessa di cancellazione non ne documenta l’esecuzione.",
                    "Chiedi al notaio come gestire la formalità e quale aggiornamento documentale occorre.", scope=scope))
            if scope and identifier:
                grouped[(json.dumps(scope, sort_keys=True), norm_text(identifier))].append((state, value))
    for (scope_key, identifier), entries in grouped.items():
        states = {s for s, _ in entries}
        if "attiva" in states and "cancellata" in states:
            findings.append(emit(property_id, "encumbrances", "vincoli.stato." + identifier, "Ricostruisci lo stato della stessa formalità", [], [v for _, v in entries],
                "Le fonti riferiscono stati diversi per la stessa formalità e unità. Potrebbe essere un aggiornamento cronologico: non viene scelto automaticamente uno stato definitivo.",
                "Confronta date, nota originaria e annotazione di cancellazione; conferma l’efficacia con il notaio.", scope=json.loads(scope_key)))
    return findings


def operational_findings(property_id, documents, property_record, today):
    findings = []
    context = (property_record or {}).get("workflow_context") or {}
    for doc in documents:
        fields, kind = _fields(doc), doc.get("document_type")
        def add(rule, field, label, paths, detail, action, **kwargs):
            findings.append(_emit(property_id, doc, rule, field, label, paths, detail, action, **kwargs))
        if kind == "contratto_locazione":
            if norm_boolean(_unwrap(fields.get("registrato"))) is False:
                add("occupancy", "locazione.registrazione", "Registrazione da verificare", ["registrato"],
                    "La fonte indica esplicitamente che il contratto non risulta registrato.", "Chiedi contratto e ricevuta di registrazione o chiarisci lo stato con il referente.")
            end = parse_date(_unwrap(fields.get("data_fine")))
            if context.get("occupancy") in {"vacant", "free", "libero"}:
                add("occupancy", "locazione.disponibilita", "Verifica la disponibilità effettiva", ["conduttore", "data_inizio", "data_fine"],
                    "La scheda indica immobile libero ma il fascicolo contiene una locazione. La sola data di fine non dimostra rilascio, risoluzione o assenza di rinnovi.",
                    "Chiedi conferma dello stato attuale e, se pertinente, risoluzione e verbale di riconsegna.")
            elif end and end < today:
                add("occupancy", "locazione.aggiornamento", "Aggiorna lo stato della locazione", ["data_fine"],
                    "Il termine riportato è trascorso; rinnovo, disdetta e riconsegna non sono dedotti automaticamente.",
                    "Acquisisci eventuali proroghe, risoluzioni e conferma dell’occupazione attuale.")
        if kind in {"preliminare_compravendita", "atto_compravendita"}:
            records = _records(doc, "condizioni_dettaglio")
            original_conditions = _unwrap(fields.get("condizioni_sospensive"))
            if original_conditions and (not records or isinstance(original_conditions, list) and len(original_conditions) > len(records)):
                add("contract_conditions", "trattativa.condizioni", "Verifica le condizioni della proposta", ["condizioni_sospensive"],
                    "Sono riportate condizioni sospensive, ma non è disponibile un esito documentato per ciascuna.",
                    "Associa a ciascuna condizione scadenza, referente e prova dell’esito; non considerarla soddisfatta per il solo trascorrere del tempo.")
            for index, record in records:
                state = norm_text(record.get("stato"))
                deadline = parse_date(record.get("data_scadenza"))
                invalid_date = bool(record.get("data_scadenza")) and deadline is None
                if state not in {"avverata", "rinunciata"} or invalid_date:
                    key = stable_id("condition", record.get("identificativo") or record.get("descrizione") or _record_key(record))
                    findings.append(emit(property_id, "contract_conditions", "trattativa.condizione." + key,
                        "Data della condizione da correggere" if invalid_date else "Condizione oltre il termine indicato" if deadline and deadline < today else "Condizione della trattativa da chiarire", [doc],
                        [_ref(doc, f"condizioni_dettaglio[{index}]", record)],
                        ("La data della condizione non è interpretabile. " if invalid_date else "La condizione non ha un esito positivo o una rinuncia esplicitamente documentati. ") + "Non viene dedotta la validità o decadenza del contratto.",
                        "Verifica la clausola, gli aggiornamenti e la prova dell’esito con le parti e il professionista incaricato.", scope=_scope(doc)))
            deadline = parse_date(_unwrap(fields.get("termine_rogito")))
            if deadline and deadline < today:
                add("contract_conditions", "trattativa.termine_rogito", "Conferma l’esito o la proroga del rogito", ["termine_rogito"],
                    "Il termine indicato nel preliminare è trascorso: il fascicolo non dimostra da questo solo dato se il rogito è avvenuto o è stato prorogato.",
                    "Collega l’atto definitivo o la proroga alla stessa operazione, poi aggiorna la pratica.")
        if kind in {"regolamento_condominio", "verbale_assemblea_condominio"}:
            if _unwrap(fields.get("limitazioni_uso")):
                add("condominium", "condominio.limitazioni", "Confronta le limitazioni con l’uso previsto", ["limitazioni_uso", "tipo_regolamento"],
                    "Il regolamento riporta limitazioni da interpretare rispetto all’attività e all’uso previsti, senza dedurne automaticamente l’applicabilità.",
                    "Mostra la clausola completa all’agente e al professionista; chiarisci efficacia e compatibilità dell’uso previsto.")
            if norm_boolean(_unwrap(fields.get("morosita_menzionata"))) is True:
                add("condominium", "condominio.morosita", "Chiarisci a chi si riferiscono gli arretrati", ["morosita_menzionata"],
                    "Il verbale menziona morosità; non è automaticamente un debito di questa unità o del venditore.",
                    "Richiedi la situazione contabile della specifica unità all’amministratore.")
            for index, record in _records(doc, "delibere"):
                total, share = parse_number(record.get("importo_totale_eur")), parse_number(record.get("quota_a_carico_unita_eur"))
                if share is not None and (share < 0 or (total is not None and share > total)):
                    findings.append(emit(property_id, "condominium", "condominio.spesa." + stable_id("resolution", _record_key(record)),
                        "Riconcilia la quota della delibera", [doc], [_ref(doc, f"delibere[{index}]", record)],
                        "La quota indicata per l’unità è negativa o superiore all’importo totale della stessa delibera.",
                        "Controlla importi, riparto e unità a cui si riferiscono.", status="conflict", scope=_scope(doc)))
        if kind == "relazione_tecnica_integrata" and _unwrap(fields.get("difformita_riscontrate")):
            add("technical_scope", "tecnica.difformita", "Leggi l’esito delle difformità riportate", ["difformita_riscontrate", "difformita_rientrano_in_tolleranza"],
                "La relazione elenca difformità; una dichiarazione generale positiva non chiarisce da sola quali siano sanate, tollerate o ancora aperte.",
                "Chiedi al tecnico l’esito documentato di ogni rilievo e gli eventuali aggiornamenti.")
        if kind == "titolo_edilizio" and norm_text(_unwrap(fields.get("stato"))) in {"in istruttoria", "decaduto", "in sanatoria", "presentato", "richiesto"}:
            add("technical_scope", "tecnica.stato_titolo", "Verifica l’esito della pratica edilizia", ["stato", "numero_pratica", "destinazione_uso"],
                "Lo stato riportato non consente al motore di trattare la pratica come un esito favorevole concluso.",
                "Richiedi al tecnico lo stato aggiornato, gli atti pertinenti e l’effetto sull’uso previsto.")
        if kind == "dichiarazione_conformita_impianti" and norm_boolean(_unwrap(fields.get("conforme"))) is False:
            add("technical_scope", "tecnica.impianti", "Approfondisci l’esito dell’impianto", ["tipo_impianto", "conforme"],
                "La dichiarazione riporta un esito negativo per l’impianto indicato.",
                "Verifica con il tecnico interventi, documentazione e stato attuale del singolo impianto.")
    return findings


def transaction_findings(property_id, documents, property_record, today: date):
    return (party_findings(property_id, documents, today) + rights_findings(property_id, documents)
            + encumbrance_findings(property_id, documents)
            + operational_findings(property_id, documents, property_record, today))
