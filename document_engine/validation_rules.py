"""Contextual checks shared by cross validation and the property checklist.

No network, new database tables, or legal certification. A finding is a reason
to review named sources, not proof that a sale or a use is unlawful.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date
import hashlib
import json
import math
from typing import Any

from core.operational_models import CrossValidationFinding, stable_id
from document_engine.cross_validation import (
    ALIASES, SPECS, _RIFERIMENTO_KEYS, _RIFERIMENTO_PARTS, _compare_field, _expand, _float,
    _unwrap, claims_from_documents, effective_facts, norm_categoria, norm_catasto_id,
    norm_comune, norm_energy_class, norm_text, parse_date, parse_number, parse_quota,
)
from document_engine.typology import typology_of

VERSION = "3.1"
PERTINENZE = frozenset({"C/2", "C/6", "C/7"})
RULES = {
    "source_eligibility": "Fonti identificate, pertinenti alla pratica e non simulate",
    "unit_scope": "Confronto separato per Comune, sezione, foglio, particella e subalterno",
    "category_use": "Categoria catastale rispetto alla tipologia e al ruolo dell’unità",
    "declared_use": "Uso dichiarato rispetto all’uso riportato nei documenti",
    "field_format": "Categorie, classi energetiche, quote e numeri interpretabili",
    "date_order": "Cronologia interna e date future di documenti già emessi",
    "amount_relation": "Caparra/prezzo e canone annuo/mensile nello stesso contratto",
    "technical_declaration": "Dichiarazioni tecniche esplicitamente negative o discordanti",
}


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def _safe_value(value):
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _safe_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_value(v) for v in value]
    return value


def claim_keys(name, value):
    keys = {key for key, _ in _expand(name, value)}
    if name in ALIASES:
        keys.add(ALIASES[name])
    return keys


def document_date(document):
    fields = document.get("extracted_fields") or {}
    for key in ("data_visura", "data_relazione", "data_emissione", "data_atto", "data_rilascio_o_presentazione", "data"):
        parsed = parse_date(_unwrap(fields.get(key)))
        if parsed:
            return parsed.isoformat()
    return None


def annotate_claims(claims, documents):
    docs = {f"doc:{d['id']}": d for d in documents}
    def origin(source, visited=()):
        if source in visited:
            return min((*visited, source))
        doc = docs.get(source, {})
        inherited = (doc.get("extracted_fields") or {}).get("_validation_origin") or {}
        if isinstance(inherited, dict) and inherited.get("document_id") is not None:
            return origin(f"doc:{inherited['document_id']}", (*visited, source))
        checksum = doc.get("content_sha256") or doc.get("checksum_sha256") or doc.get("file_sha256")
        return f"sha256:{checksum}" if checksum else source
    for claim in claims:
        doc = docs.get(claim.source_key, {})
        claim.independence_key = origin(claim.source_key)
        claim.as_of = document_date(doc)
        claim.document_type = claim.document_type or doc.get("document_type")
    return claims


def emit(property_id, rule, field, label, documents, values, detail, action,
         *, status="attention", severity="high", scope=None):
    sources = sorted({v["source_key"] for v in values if v.get("source_key")})
    known = [v["confidence"] for v in values if v.get("confidence") is not None]
    uncertain = any(v < .4 for v in known)
    if uncertain and status in {"conflict", "invalid"}:
        status = "attention"
        detail += " La lettura è incerta: confermare prima il testo originale."
    return CrossValidationFinding(
        finding_id=stable_id("context-validation", property_id, rule, field, _json(scope or {}), *sources),
        property_id=property_id, rule_id=rule, rule_version=VERSION, field=field,
        label=label, status=status, severity=severity, confidence=min(known) if known else 0.0,
        scope=scope or {}, sources=sources, values=values,
        evidence_ids=sorted({str(e) for v in values for e in v.get("evidence_ids", [])}),
        detail=detail, recommended_action=action,
    )


def value_ref(document, path, raw):
    wrapper = raw if isinstance(raw, dict) else {}
    confidence = wrapper.get("confidence", document.get("extraction_confidence"))
    return {"source_key": f"doc:{document['id']}", "source": document.get("file_name") or f"Documento {document['id']}",
            "source_path": path, "value": _safe_value(_unwrap(raw)), "document_type": document.get("document_type"),
            "page": wrapper.get("source_page", wrapper.get("page")),
            "source_text": wrapper.get("fonte", wrapper.get("source_text")),
            "confidence": _float(confidence), "evidence_ids": wrapper.get("evidence_ids") or [],
            "fact_id": wrapper.get("fact_id"), "as_of": document_date(document)}


def eligible_sources(property_id, facts, documents):
    """Prevent foreign, rejected, pending and simulated sources confirming a property."""
    accepted, findings, blocked = [], [], set()
    for doc in documents:
        key = str(doc.get("id"))
        meta = doc.get("metadata") or {}
        if not isinstance(meta, dict):
            meta = {}
        mode = str(doc.get("environment") or meta.get("environment") or doc.get("source_mode") or "").lower()
        reason = None
        if doc.get("id") is None:
            reason = "Documento senza identificativo: impossibile attribuire correttamente le prove."
        elif doc.get("property_id") is not None and str(doc["property_id"]) != str(property_id):
            reason = "Il documento risulta collegato a un altro immobile."
        elif mode in {"sandbox", "simulated", "simulation", "fixture", "test", "demo"}:
            reason = "Dati simulati: esclusi dalle verifiche dell’immobile reale."
        elif str(doc.get("processing_status") or "").lower() in {"failed", "rejected", "queued", "processing", "running"}:
            reason = "Analisi del documento non completata o rifiutata."
        elif doc.get("processing_status") == "completed" and not doc.get("extracted_fields"):
            reason = "Analisi terminata senza dati estratti utilizzabili."
        elif doc.get("extracted_fields") is not None and not isinstance(doc.get("extracted_fields"), dict):
            reason = "Formato dei dati estratti non utilizzabile: ripetere l’analisi."
        if reason:
            blocked.add(key)
            source = f"doc:{key}" if doc.get("id") is not None else "unidentified:" + hashlib.sha256(_json(doc).encode()).hexdigest()[:16]
            findings.append(emit(property_id, "source_eligibility", "documento.ammissibilita", "Fonte da verificare", [],
                [{"source_key": source, "value": doc.get("file_name")}], reason,
                "Verifica il collegamento alla pratica e completa l’analisi del documento originale."))
        else:
            accepted.append({**doc, "document_type": str(doc.get("document_type") or "").lower(),
                             "extracted_fields": doc.get("extracted_fields") if isinstance(doc.get("extracted_fields"), dict) else {}})
    kept = []
    for fact in facts:
        if str(fact.get("source_document_id")) in blocked:
            continue
        if fact.get("property_id") is not None and str(fact["property_id"]) != str(property_id):
            continue
        if str(fact.get("environment") or fact.get("source_mode") or "").lower() in {"sandbox", "test", "demo", "simulated", "simulation", "fixture"}:
            continue
        kept.append(fact)
    return kept, accepted, findings


def effective_documents(documents, facts):
    """Apply feedback and persisted fields also to contextual checks, without choosing
    a winner between contradictory extractions. Preserve field-level provenance."""
    groups = defaultdict(list)
    for fact in facts:
        if fact.get("source_document_id") is not None:
            groups[str(fact["source_document_id"])].append(fact)
    result = []
    for doc in documents:
        fields = deepcopy(doc.get("extracted_fields") or {})
        group = groups.get(str(doc.get("id")), [])
        for fact in group:
            name = fact.get("fact_name") or fact.get("field") or ""
            represented = claim_keys(name, fact.get("fact_value", fact.get("value")))
            for key in list(fields):
                if key == name:
                    del fields[key]
                elif key in _RIFERIMENTO_KEYS:
                    value = _unwrap(fields[key])
                    for ref in value if isinstance(value, list) else [value]:
                        if isinstance(ref, dict):
                            for part, canonical in _RIFERIMENTO_PARTS.items():
                                if canonical in represented:
                                    ref.pop(part, None)
                elif claim_keys(key, fields[key]) & represented:
                    del fields[key]
        by_name = defaultdict(list)
        effective = effective_facts(group)
        verified = {key for fact in effective if fact.get("verification_status") in {"verified", "corrected"}
                    for key in claim_keys(fact.get("fact_name") or fact.get("field") or "", fact.get("fact_value", fact.get("value")))}
        for fact in effective:
            name = fact.get("fact_name") or fact.get("field") or ""
            if name in ALIASES and ALIASES[name] in verified and fact.get("verification_status") not in {"verified", "corrected"}:
                continue
            # Group aliases too: conflicting aliases must not silently choose a winner.
            by_name[ALIASES.get(name, name)].append(fact)
        # Containers first, scalar corrections second, independently of input order.
        for _, entries in sorted(by_name.items(), key=lambda pair: (pair[0] not in _RIFERIMENTO_KEYS, pair[0])):
            name = entries[0].get("fact_name") or entries[0].get("field") or ""
            values = {_json(_unwrap(f.get("fact_value", f.get("value")))) for f in entries}
            if len(values) != 1:
                continue
            item = sorted(entries, key=lambda f: str(f.get("id", "")))[0]
            prov = item.get("provenance") or {}
            wrapper = {"value": _unwrap(item.get("fact_value", item.get("value"))),
                            "confidence": item.get("confidence_score", item.get("confidence")),
                            "fact_id": str(item["id"]) if item.get("id") is not None else None,
                            "evidence_ids": item.get("evidence_ids") or [],
                            "source_page": prov.get("source_page"), "source_text": prov.get("source_text")}
            # A field correction on one identified unit must preserve its other
            # cadastral coordinates. Never assign an unscoped fact to many units.
            refs = [ref for key, raw in fields.items() if key in _RIFERIMENTO_KEYS
                    for ref in (_unwrap(raw) if isinstance(_unwrap(raw), list) else [_unwrap(raw)]) if isinstance(ref, dict)]
            canonical = ALIASES.get(name, "")
            part = next((p for p, c in _RIFERIMENTO_PARTS.items() if c == canonical), None)
            if len(refs) == 1 and canonical.startswith("catasto.") and part:
                refs[0][part] = wrapper
            else:
                fields[name] = wrapper
        result.append({**doc, "extracted_fields": fields})
    return result


def unit_records(document):
    fields = document.get("extracted_fields") or {}
    result = []
    for name in sorted(_RIFERIMENTO_KEYS):
        raw = fields.get(name)
        value = _unwrap(raw)
        for index, ref in enumerate(value if isinstance(value, list) else [value]):
            if not isinstance(ref, dict):
                continue
            identity = {k: norm_catasto_id(_unwrap(ref.get(k))) or "" for k in ("sezione", "foglio", "particella", "subalterno")}
            identity["comune"] = norm_comune(_unwrap(ref.get("comune"))) or ""
            complete = all(identity[k] for k in ("comune", "foglio", "particella", "subalterno"))
            result.append({"identity": identity, "complete": complete, "ref": ref,
                           "path": f"{name}[{index}]" if isinstance(value, list) else name,
                           "wrapper": raw if isinstance(raw, dict) and "value" in raw else {}})
    # Older extractors can emit cadastral fields at the top level.
    if not result and any(k in fields for k in ("categoria", "category", "categoria_catastale")):
        ref = {k: _unwrap(fields.get(k)) for k in ("comune", "sezione", "foglio", "particella", "subalterno")}
        ref["categoria"] = _unwrap(fields.get("categoria", fields.get("category", fields.get("categoria_catastale"))))
        return unit_records({**document, "extracted_fields": {"riferimento": ref}})
    return result


def unit_comparisons(property_id, documents):
    """Compare fully identified units separately. Unknown scopes remain reviewable."""
    entries = [(doc, item) for doc in documents for item in unit_records(doc)]
    complete = {(str(d["id"]), _json(u["identity"])) for d, u in entries if u["complete"]}
    identities = {identity for _, identity in complete}
    multi = {str(d["id"]) for d in documents if len({_json(u["identity"]) for u in unit_records(d)}) > 1}
    if len(identities) <= 1 and not multi:
        return set(), []
    excluded = {f"doc:{d['id']}" for d, _ in entries}
    findings, grouped = [], defaultdict(list)
    for doc, item in entries:
        if not item["complete"]:
            continue
        clone = {**doc, "extracted_fields": {"riferimento": item["ref"]}}
        if len(unit_records(doc)) == 1:
            clone["extracted_fields"].update({k: v for k, v in doc["extracted_fields"].items() if k not in _RIFERIMENTO_KEYS})
        claims = annotate_claims(claims_from_documents([clone]), documents)
        for claim in claims:
            claim.source_path = item["path"] + "." + claim.field.removeprefix("catasto.") if claim.field.startswith("catasto.") else claim.source_path
            wrapper = item["wrapper"]
            if wrapper and claim.field.startswith("catasto."):
                claim.confidence = _float(wrapper.get("confidence"))
                claim.fact_id = wrapper.get("fact_id")
                claim.evidence_ids = wrapper.get("evidence_ids") or []
                claim.page = wrapper.get("source_page")
                claim.source_text = wrapper.get("source_text")
            grouped[(_json(item["identity"]), claim.field)].append(claim)
    for (identity, field), claims in sorted(grouped.items()):
        if len({c.source_key for c in claims}) < 2:
            continue
        for finding in _compare_field(property_id, SPECS[field], claims):
            finding.scope = json.loads(identity)
            finding.finding_id = stable_id(finding.finding_id, identity)
            findings.append(finding)
    for doc in documents:
        refs = unit_records(doc)
        if not refs:
            continue
        unmatched = any(not u["complete"] or sum(1 for _, key in complete if key == _json(u["identity"])) < 2 for u in refs)
        if str(doc["id"]) in multi or unmatched:
            findings.append(emit(property_id, "unit_scope", "catasto.unita_multiple" if str(doc["id"]) in multi else "catasto.ambito",
                "Identifica le unità della pratica", [doc], [value_ref(doc, u["path"], u["ref"]) for u in refs],
                "Le unità complete sono confrontate separatamente. Dati incompleti, unità senza riscontro e valori globali non attribuiti richiedono verifica.",
                "Associa l’unità principale e le pertinenze tramite Comune, sezione, foglio, particella e subalterno."))
    return excluded, findings


def category_findings(property_id, property_record, documents):
    if not property_record:
        return []
    typology = typology_of(property_record)
    entries = [(d, u) for d in documents for u in unit_records(d)]
    target_ref = {"comune": property_record.get("comune_catastale") or property_record.get("city"),
                  "sezione": property_record.get("sezione"), "foglio": property_record.get("foglio"),
                  "particella": property_record.get("particella") or property_record.get("mappale"), "subalterno": property_record.get("subalterno")}
    target = unit_records({"extracted_fields": {"riferimento": target_ref}})[0]
    compatible = [u for _, u in entries if norm_categoria(_unwrap(u["ref"].get("categoria"))) in typology.categories
                  and u["complete"] and _unwrap(u["ref"].get("ruolo_unita")) != "pertinenza"]
    findings = []
    for doc, unit in entries:
        raw = unit["ref"].get("categoria")
        category = norm_categoria(_unwrap(raw))
        if not category or category in typology.categories:
            continue
        explicit_main = _unwrap(unit["ref"].get("ruolo_unita")) == "principale" or (
            target["complete"] and unit["complete"] and target["identity"] == unit["identity"])
        accessory = category in PERTINENZE and not explicit_main
        # A different, fully identified dwelling can support the accessory interpretation.
        if accessory and unit["complete"] and any(u["identity"] != unit["identity"] and
            all(u["identity"][k] == unit["identity"][k] for k in ("comune", "sezione", "foglio", "particella")) for u in compatible):
            continue
        value = value_ref(doc, unit["path"] + ".categoria", {**unit["wrapper"], **(raw if isinstance(raw, dict) else {}), "value": category})
        as_of = document_date(doc)
        historical = unit["complete"] and as_of and any(
            u["complete"] and u["identity"] == unit["identity"] and document_date(d) and document_date(d) > as_of
            and norm_categoria(_unwrap(u["ref"].get("categoria"))) in typology.categories for d, u in entries)
        findings.append(emit(property_id, "category_use", "catasto.uso_dichiarato", f"Categoria {category}: verifica l’uso dichiarato", [doc], [value],
            (f"La scheda indica {typology.label.lower()}, mentre l’unità principale risulta {category}. " if explicit_main else
             f"La scheda indica {typology.label.lower()}, ma la fonte riporta {category}. ") +
            ("Potrebbe essere una pertinenza: manca l’associazione documentata con l’unità principale. " if accessory else "") +
            ("Una fonte successiva per la stessa unità riporta una categoria diversa: ricostruire la variazione. " if historical else "") +
            "La categoria catastale non prova da sola la destinazione urbanistica legittima.",
            f"Confronta i subalterni, la planimetria e i titoli edilizi; chiedi al tecnico di confermare l’uso legittimo previsto per {typology.label.lower()}.",
            status="attention" if accessory or historical else "conflict", scope=unit["identity"]))
    return findings


def norm_use(value):
    text = norm_text(_unwrap(value))
    # Exact supported meanings only. Never infer from 'non abitativo', project
    # descriptions, hypothetical changes of use, or arbitrary LLM prose.
    groups = {"abitativo": {"abitativo", "abitativa", "residenziale", "abitazione", "uso abitativo", "civile abitazione"},
              "deposito": {"deposito", "magazzino", "magazzino deposito"},
              "ufficio": {"ufficio", "direzionale", "studio professionale"},
              "negozio": {"negozio", "commerciale", "uso commerciale"},
              "produttivo": {"produttivo", "industriale", "laboratorio", "artigianale"},
              "box": {"box", "autorimessa", "garage", "posto auto"}}
    return next((key for key, values in groups.items() if text in values), None)


def contextual_findings(property_id, documents, property_record, today):
    findings = category_findings(property_id, property_record, documents)
    expected_use = {"appartamento": "abitativo", "villa": "abitativo", "box": "box", "negozio": "negozio",
                    "ufficio": "ufficio", "magazzino": "deposito", "laboratorio": "produttivo", "capannone": "produttivo"}.get(typology_of(property_record or {}).key)
    for doc in documents:
        fields = doc["extracted_fields"]
        def add(rule, field, label, keys, detail, action, status="attention", severity="high"):
            findings.append(emit(property_id, rule, field, label, [doc], [value_ref(doc, k, fields.get(k)) for k in keys],
                                 detail, action, status=status, severity=severity))
        for unit in unit_records(doc):
            raw = _unwrap(unit["ref"].get("categoria"))
            if raw not in (None, "") and not norm_categoria(raw):
                findings.append(emit(property_id, "field_format", "catasto.categoria_formato", "Categoria catastale non interpretabile", [doc],
                    [value_ref(doc, unit["path"] + ".categoria", {**unit["wrapper"], "value": raw})],
                    "Il valore non identifica una categoria catastale completa riconosciuta.", "Rileggi la categoria sulla visura originale.", status="invalid"))
        for key, raw in fields.items():
            value = _unwrap(raw)
            if value in (None, "", []):
                continue
            canonical = ALIASES.get(key)
            if canonical == "classe_energetica" and not norm_energy_class(value):
                add("field_format", "ape.classe_formato", "Classe energetica non interpretabile", [key],
                    "La lettura non contiene una classe energetica valida e completa.", "Controlla la classe sull’APE originale.", "invalid")
            if canonical in SPECS and (canonical.startswith("superficie") or canonical in {"prezzo_eur", "canone_mensile_eur", "epgl", "catasto.rendita_eur"}):
                number = parse_number(value)
                bad = number is None or number < 0 or (number == 0 and canonical.startswith("superficie"))
                if bad:
                    add("field_format", canonical + ".formato", "Valore numerico da verificare", [key],
                        "Il valore è assente, non interpretabile o incompatibile con la grandezza dichiarata.", "Confronta cifra, unità di misura e separatori con il documento originale.", "invalid")
            if canonical == "quota_proprieta" or key == "diritti_e_quote":
                quota = parse_quota(value)
                if quota is not None and not 0 < quota <= 1 or (isinstance(value, str) and "/0" in value.replace(" ", "")):
                    add("field_format", "quota_proprieta.formato", "Quota non valida", [key],
                        "La quota numerica non è compresa tra zero escluso e l’intero.", "Verifica diritto, soggetto e quota sul documento.", "invalid")
            if key.startswith("data_") or key in {"termine_rogito", "data"}:
                parsed = parse_date(value)
                if parsed is None:
                    add("field_format", "documento.data_formato." + key, "Data non interpretabile", [key],
                        "La data estratta non è una data di calendario valida o completa.", "Conferma giorno, mese e anno sul documento.", "invalid", "medium")
                elif key in {"data_emissione", "data_visura", "data_atto", "data_relazione", "data_rilascio", "data_deposito"} and parsed > today:
                    add("date_order", "documento.data_futura." + key, "Data del documento nel futuro", [key],
                        "La data di un documento presentato come già emesso è successiva alla data della verifica.", "Verifica se è una bozza o un errore OCR.")
        for start, end in (("data_emissione", "data_scadenza"), ("data_inizio", "data_fine"), ("data", "termine_rogito")):
            a, b = parse_date(_unwrap(fields.get(start))), parse_date(_unwrap(fields.get(end)))
            if a and b and b < a:
                add("date_order", "documento.cronologia." + end, "Date in ordine incompatibile", [start, end],
                    "La data finale precede quella iniziale nello stesso documento.", "Controlla le due date e le eventuali rettifiche nel documento originale.", "conflict")
        for total_key, part_key, factor in (("prezzo_eur", "caparra_eur", None), ("canone_annuo_eur", "canone_mensile_eur", 12)):
            total, part = parse_number(_unwrap(fields.get(total_key))), parse_number(_unwrap(fields.get(part_key)))
            if total is not None and part is not None and (part > total if factor is None else abs(total - factor * part) > .02):
                add("amount_relation", "economia." + part_key, "Importi da riconciliare", [total_key, part_key],
                    "La caparra supera il prezzo indicato." if factor is None else "Il canone annuo non coincide con dodici mensilità: verificare spese, sconti e periodicità.",
                    "Confronta le clausole economiche, le componenti incluse e gli importi originali.", "conflict" if factor is None else "attention")
        for key in ("conformita_catastale", "conformita_urbanistica", "stato_legittimo_verificato"):
            if _unwrap(fields.get(key)) is False:
                add("technical_declaration", "tecnica." + key, "Verifica tecnica aperta", [key],
                    "Il documento tecnico riporta esplicitamente un esito negativo o una verifica non completata.", "Apri la relazione, individua il rilievo e chiedi al tecnico le verifiche o gli interventi necessari.")
        for key in ("uso", "destinazione_uso", "destinazione_uso_legittima"):
            actual = norm_use(fields.get(key))
            if property_record and actual and expected_use and actual != expected_use:
                add("declared_use", "uso.destinazione", "Uso documentato diverso da quello della scheda", [key],
                    f"La fonte riporta uso {actual}; la scheda della pratica indica {expected_use}. Potrebbe riguardare un’altra unità, una situazione storica o un cambio d’uso.",
                    "Associa il documento all’unità corretta e chiedi al tecnico di verificare lo stato attuale e i titoli pertinenti.")
    return findings
