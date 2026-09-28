"""Compare preliminary/final deeds only after an explicit operation link.

The same property can have many transactions. Dates or matching prices alone
never establish that two contracts are the same operation.
"""
from collections import defaultdict
from datetime import date
import json

from document_engine.cross_validation import (
    SPECS, _claim, _compare_field, _unwrap, parse_date,
)
from document_engine.validation_rules import (
    VERSION, annotate_claims, document_date, emit, unit_records, value_ref,
)
from document_engine.transaction_validation import _records, _ref


def unit_set(document):
    units = unit_records(document)
    if not units or any(not u["complete"] for u in units):
        return ()
    return tuple(sorted({json.dumps(u["identity"], sort_keys=True) for u in units}))


def operation_link(document):
    raw = (document.get("extracted_fields") or {}).get("collegamento_operazione")
    record = _unwrap(raw)
    if not isinstance(record, dict):
        return {}
    parent = raw if isinstance(raw, dict) else {}
    return {**{k: v for k, v in parent.items() if k not in {"value", "valore"}}, **record}


def operation_key(document):
    link = operation_link(document)
    reference = link.get("riferimento")
    when = parse_date(link.get("data"))
    if not isinstance(reference, str) or not reference.strip() or not when:
        return None
    # Preserve punctuation: RP/123 and RP-123 may identify different records.
    return (" ".join(reference.casefold().split()), when.isoformat())


def _scope(key, units=()):
    return {"operation_ref": key[0], "operation_date": key[1],
            **({"unit_set": json.dumps([json.loads(u) for u in units], sort_keys=True)} if units else {})}


def _link_value(document):
    return _ref(document, "collegamento_operazione", operation_link(document))


def operation_findings(property_id, documents, today: date):
    groups, findings = defaultdict(list), []
    for doc in documents:
        if doc.get("document_type") not in {"preliminare_compravendita", "atto_compravendita"}:
            continue
        link = operation_link(doc)
        if not any(link.get(k) for k in ("riferimento", "data", "stato_documento")):
            continue
        key = operation_key(doc)
        if not key or not unit_set(doc):
            findings.append(emit(property_id, "operation_scope", "operazione.collegamento", "Completa il collegamento dell’operazione", [doc], [_link_value(doc)],
                "Mancano estremi completi dell’operazione o identificativi completi di tutte le unità. Non si collegano contratti per sola somiglianza.",
                "Verifica il richiamo esplicito al preliminare e le unità comprese nel contratto."))
            continue
        groups[key].append(doc)
    for key, docs in sorted(groups.items()):
        preliminaries = sorted((d for d in docs if d["document_type"] == "preliminare_compravendita"), key=lambda d: str(d["id"]))
        finals = sorted((d for d in docs if d["document_type"] == "atto_compravendita"), key=lambda d: str(d["id"]))
        for pre in preliminaries:
            for final in finals:
                units = unit_set(pre)
                scope = _scope(key, units)
                links = [_link_value(pre), _link_value(final)]
                if units != unit_set(final):
                    findings.append(emit(property_id, "operation_scope", "operazione.oggetto", "Le unità dell’operazione non coincidono", [pre, final], links + [
                        value_ref(d, u["path"], u["ref"]) for d in (pre, final) for u in unit_records(d)],
                        "I documenti richiamano gli stessi estremi, ma includono insiemi diversi di unità. Potrebbe essere una modifica dell’oggetto, una pertinenza esclusa o un errore di lettura.",
                        "Confronta l’oggetto completo e le eventuali modifiche prima di confrontare prezzo e parti.", scope=scope))
                    continue
                pre_date, final_date = parse_date(document_date(pre)), parse_date(document_date(final))
                reliable_link = all(v.get("confidence") is not None and v["confidence"] >= .8 and v.get("source_text") for v in links)
                signed = all(operation_link(d).get("stato_documento") == "sottoscritto" for d in (pre, final))
                chronological = pre_date is not None and final_date is not None and pre_date == parse_date(key[1]) and pre_date <= final_date <= today
                if not signed or not chronological or not reliable_link:
                    findings.append(emit(property_id, "operation_scope", "operazione.verificabilita", "Conferma firme, date e richiamo contrattuale", [pre, final], links + [
                        value_ref(pre, "data", pre["extracted_fields"].get("data")), value_ref(final, "data_atto", final["extracted_fields"].get("data_atto"))],
                        "Bozze, date non coerenti, lettura incerta o richiamo privo di citazione non dimostrano un passaggio dal preliminare al definitivo.",
                        "Controlla gli originali sottoscritti e il richiamo alla stessa operazione; completa le date e le citazioni.", scope=scope))
                    continue
                mapping = (("promittente_venditore", "parte_venditrice", "proprietari", "venditori"),
                           ("promittente_acquirente", "parte_acquirente", "proprietari", "acquirenti"),
                           ("prezzo_eur", "prezzo_eur", "prezzo_eur", "prezzo"))
                missing = []
                for left, right, canonical, label in mapping:
                    values = [value_ref(d, name, d["extracted_fields"].get(name)) for d, name in ((pre, left), (final, right))]
                    claims = [_claim(canonical, v["value"], source_key=v["source_key"], source_label=v["source"],
                        confidence=v["confidence"], source_path=v["source_path"], page=v["page"],
                        source_text=v["source_text"], fact_id=v["fact_id"], evidence_ids=v["evidence_ids"]) for v in values]
                    if any(c is None for c in claims):
                        missing.append(label)
                        continue
                    claims = annotate_claims(claims, documents)
                    for comparison in _compare_field(property_id, SPECS[canonical], claims):
                        status = comparison.status
                        if status in {"conflict", "compatible"}:
                            status = "attention"
                        uncertain = any(v.get("confidence") is None or v["confidence"] < .8 for v in values)
                        if status == "consistent" and uncertain:
                            status = "attention"
                        findings.append(emit(property_id, "operation_comparison", "operazione." + label,
                            "Preliminare e definitivo: " + label, [pre, final], values + links,
                            comparison.detail + (" La lettura di almeno un valore va confermata prima di usare il confronto." if uncertain else "") + " Il confronto riguarda solo gli estremi e le unità collegati; modifiche pattuite, rappresentanza e nuovi accordi vanno verificati.",
                            "Leggi le clausole e le eventuali modifiche con le parti e il professionista incaricato.", status=status,
                            severity="low" if status == "consistent" else "high", scope=scope))
                if missing:
                    findings.append(emit(property_id, "operation_comparison", "operazione.dati_mancanti", "Completa i dati del confronto contrattuale", [pre, final], links,
                        "Non sono leggibili in entrambe le fonti: " + ", ".join(missing) + ".",
                        "Recupera i campi e le rispettive citazioni dagli originali.", scope=scope))
                # A documented outcome is evidence to review, not an automatic
                # resolution of a legal condition or of its older warning.
                previous = defaultdict(list)
                for pre_index, record in _records(pre, "condizioni_dettaglio"):
                    if record.get("identificativo"):
                        previous[str(record["identificativo"])].append((pre_index, record))
                for index, outcome in _records(final, "condizioni_dettaglio"):
                    identifier = str(outcome.get("identificativo") or "")
                    if len(previous.get(identifier, [])) != 1:
                        continue
                    recorded_states = {record.get("stato") for other in finals if unit_set(other) == units
                        and operation_link(other).get("stato_documento") == "sottoscritto"
                        for _, record in _records(other, "condizioni_dettaglio") if str(record.get("identificativo") or "") == identifier}
                    if len(recorded_states) > 1:
                        # Contradictory reported outcomes are not a closure proof.
                        values = [_ref(other, f"condizioni_dettaglio[{i}]", record) for other in finals if unit_set(other) == units
                            and operation_link(other).get("stato_documento") == "sottoscritto"
                            for i, record in _records(other, "condizioni_dettaglio") if str(record.get("identificativo") or "") == identifier]
                        findings.append(emit(property_id, "operation_condition_history", "operazione.esiti_diversi." + identifier,
                            "Ricostruisci gli esiti della stessa condizione", finals, values,
                            "Le fonti collegate riportano esiti diversi per la stessa condizione. Potrebbe trattarsi di una modifica nel tempo; nessun esito viene scelto automaticamente.",
                            "Confronta clausola, date e aggiornamenti con le parti e il professionista incaricato.",
                            scope={**scope, "condition_ref": identifier}))
                        continue
                    pre_index, pre_record = previous[identifier][0]
                    previous_value = _ref(pre, f"condizioni_dettaglio[{pre_index}]", pre_record)
                    value = _ref(final, f"condizioni_dettaglio[{index}]", outcome)
                    origins = annotate_claims([_claim("prezzo_eur", 1, source_key=f"doc:{d['id']}", source_label="") for d in (pre, final)], documents)
                    independent = len({c.independence_key for c in origins}) == 2
                    supported = outcome.get("stato") in {"avverata", "rinunciata"} and all(v.get("source_text") and v.get("confidence") is not None and v["confidence"] >= .8 for v in (previous_value, value))
                    if supported and independent:
                        findings.append(emit(property_id, "operation_condition_evidence", "operazione.esito_condizione." + identifier,
                            "È disponibile una fonte sull’esito della condizione", [pre, final], [previous_value, value] + links,
                            "Il definitivo collegato riporta un esito esplicito per la stessa condizione. La prova è disponibile per la revisione; il punto non viene chiuso automaticamente.",
                            "Apri la citazione del definitivo e fai confermare l’esito della clausola al referente della pratica.",
                            severity="medium", scope={**scope, "condition_ref": identifier}))
    return findings
