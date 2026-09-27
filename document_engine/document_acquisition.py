"""Document acquisition rules. Requests are drafts, never outbound messages."""
from collections import defaultdict
from core.operational_models import DocumentRequest
from document_engine.operational_services import APE_REGISTRY, PROVINCE_REGION
from document_engine.request_composer import compose_request_message, content_hash, field_gaps_for_item
from document_engine.typology import TYPOLOGIES, typology_of
from integrations import openapi_catasto

_NOT_BOX = frozenset(TYPOLOGIES) - {"box"}  # A garage/parking space does not need an APE.
_RETAIL_LIKE = frozenset({"negozio", "ufficio", "centro_commerciale"})
_LARGE_OR_INDUSTRIAL = frozenset({"capannone", "magazzino", "centro_commerciale"})
_APE_REGIONAL_URL = {"ER": "https://sace-er.regione.emilia-romagna.it/ui/ape/public-registry",
                     "LOM": "https://areaoperativa.cened.it/extcatasto/html/public/visuraApe.jsf"}

# Operational catalogue, not a declaration of legal obligations.
# Each row: key, title, recipient, package, condition, aliases, typologies (None = every typology).
CATALOGUE = [
    ("ape", "APE completo", "seller", "energy", None, ("ape_energy_certificate",), _NOT_BOX),
    ("visura_catastale", "Visura catastale", "professional", "cadastral", None, ("visura",), None),
    ("planimetria_catastale", "Planimetria catastale", "seller", "cadastral", None, ("planimetria",), None),
    ("elaborato_planimetrico", "Elaborato planimetrico", "professional", "cadastral", "sale", (), None),
    ("ispezione_ipotecaria", "Ispezione ipotecaria", "professional", "cadastral", "sale", ("visura_ipotecaria",), None),
    ("atto_provenienza", "Atto di provenienza", "seller", "ownership", None, ("atto_compravendita", "atto_proprieta"), None),
    ("titoli_edilizi", "Titoli edilizi e varianti disponibili", "seller", "planning", "sale", ("permesso_costruire",), None),
    ("agibilita", "Documentazione di agibilità disponibile", "seller", "planning", "sale", (), None),
    ("regolamento_condominiale", "Regolamento condominiale", "administrator", "condominium", "condominium", (), None),
    ("verbali_assembleari", "Ultimi verbali assembleari", "administrator", "condominium", "condominium", (), None),
    ("consuntivo_condominiale", "Ultimo consuntivo", "administrator", "condominium", "condominium", (), None),
    ("preventivo_condominiale", "Preventivo condominiale", "administrator", "condominium", "condominium", (), None),
    ("dichiarazione_spese_liti", "Situazione spese, lavori deliberati e liti", "administrator", "condominium", "condominium", (), None),
    ("documentazione_impianti", "Documentazione impianti disponibile", "seller", "systems", None, (), None),
    ("libretto_impianto", "Libretto impianto", "seller", "systems", "heating", (), None),
    ("contratto_locazione", "Contratto di locazione in essere", "seller", "tenancy", "occupied", (), None),
    ("ricevuta_rli", "Ricevuta registrazione contratto", "seller", "tenancy", "occupied", ("rli",), None),
    ("successione", "Documentazione della successione", "seller", "ownership", "inheritance", (), None),
    ("donazione", "Atto di donazione", "seller", "ownership", "donation", (), None),
    ("procura", "Procura", "seller", "ownership", "proxy", (), None),
    ("visura_camerale", "Visura camerale e poteri di firma", "professional", "ownership", "company", (), None),
    ("scia_licenza_commerciale", "SCIA o licenza per l'attività commerciale", "seller", "planning", None, (), _RETAIL_LIKE),
    ("certificato_prevenzione_incendi", "Certificato di prevenzione incendi (CPI/SCIA antincendio)", "seller", "planning", None, (), _LARGE_OR_INDUSTRIAL),
]


def canonical_type(value):
    value = str(value or "").strip().casefold().replace(" ", "_")
    for key, _, _, _, _, aliases, _ in CATALOGUE:
        if value == key or value in aliases:
            return key
    return value


def build_document_packages(property_record, documents, existing_requests):
    purpose = property_record.get("purpose") or property_record.get("transaction_type")
    typology_key = typology_of(property_record).key
    conditions = {
        "sale": purpose in {"sale", "vendita", "acquisto"},
        "condominium": property_record.get("is_condominium"),
        "heating": property_record.get("has_heating"),
        "occupied": property_record.get("is_rented"),
        "inheritance": property_record.get("ownership_origin") == "inheritance" if property_record.get("ownership_origin") else None,
        "donation": property_record.get("ownership_origin") == "donation" if property_record.get("ownership_origin") else None,
        "proxy": property_record.get("has_proxy"),
        "company": property_record.get("seller_type") == "company" if property_record.get("seller_type") else None,
    }
    present = {canonical_type(d.get("document_type")) for d in documents
               if d.get("processing_status") not in {"failed", "rejected"}}
    existing = {canonical_type(r.get("document_type")): r for r in existing_requests}
    packages = defaultdict(list)
    checks = []
    for key, title, recipient, package, condition, _, typologies in CATALOGUE:
        if typologies is not None and typology_key not in typologies:
            continue
        if condition and conditions[condition] is not True:
            if conditions[condition] is None or (condition == "sale" and not purpose):
                checks.append({"document_type": key, "condition": condition})
            continue
        previous = existing.get(key)
        status = "present" if key in present else (previous["status"] if previous else "draft")
        gaps = None
        if status == "present":
            matching = [d for d in documents if canonical_type(d.get("document_type")) == key]
            gaps = field_gaps_for_item(key, matching, property_id=property_record["id"])
        packages[recipient].append({"document_type": key, "title": title, "package": package,
            "status": status, "request_id": previous.get("request_id") if previous else None,
            "source": acquisition_source(key, property_record), "field_gaps": gaps})
    groups = []
    for recipient, items in packages.items():
        missing = [i for i in items if i["status"] in {"draft", "open"}]
        incomplete = [i for i in items if i.get("field_gaps")]
        missing_titles = [i["title"] for i in missing]
        field_gaps = {i["title"]: i["field_gaps"] for i in incomplete}
        fallback = None
        if missing_titles:
            fallback = "Documenti richiesti per la pratica: \n" + "\n".join("- " + t for t in missing_titles)
        if field_gaps:
            gap_lines = "\n".join(
                f"- {title}: " + "; ".join(gaps.get("essenziali", []) + gaps.get("accessorie", []))
                for title, gaps in field_gaps.items())
            fallback = (fallback + "\n\n" if fallback else "") + "Documenti già ricevuti ma da completare:\n" + gap_lines
        groups.append({"recipient_role": recipient, "items": items,
            "missing_titles": missing_titles, "field_gaps": field_gaps,
            "content_hash": content_hash(recipient, missing_titles, field_gaps) if fallback else None,
            "draft_message": fallback})
    return {"property_id": property_record["id"], "packages": groups,
            "applicability_checks": checks, "delivery_status": "not_sent"}


def apply_request_messages(plan: dict, property_record: dict, stored_messages: list[dict],
                           *, generate: bool) -> tuple[dict, list[dict]]:
    """Overlay cached (or freshly composed, if `generate`) AI letters onto the
    plan's deterministic draft_message. Never calls the AI on a plain read
    (`generate=False`): the GET endpoint only ever serves what's cached, so
    loading the page is free and instant. Returns the updated plan plus any
    newly composed rows the caller should upsert into
    smartbuy_request_messages."""
    stored = {row["recipient_role"]: row for row in stored_messages}
    to_persist: list[dict] = []
    for group in plan["packages"]:
        hash_value = group.get("content_hash")
        if hash_value is None:
            continue  # nothing missing for this recipient right now
        cached = stored.get(group["recipient_role"])
        if cached and cached.get("content_hash") == hash_value:
            group["draft_message"] = cached["message"]
            continue
        if not generate:
            continue  # stale or absent cache, but not asked to regenerate: keep the deterministic fallback
        composed = compose_request_message(
            recipient_role=group["recipient_role"], property_record=property_record,
            missing_titles=group["missing_titles"], field_gaps=group["field_gaps"])
        if composed:
            group["draft_message"] = composed
            to_persist.append({"property_id": plan["property_id"], "recipient_role": group["recipient_role"],
                                "message": composed, "content_hash": hash_value})
    return plan, to_persist


def persist_request_drafts(client, plan):
    rows = []
    for group in plan["packages"]:
        for item in group["items"]:
            if item["status"] != "draft":
                continue
            rows.append(DocumentRequest.create(property_id=plan["property_id"],
                document_type=item["document_type"], requested_from=group["recipient_role"],
                reason=item["title"]).model_dump(mode="json"))
    if rows:
        # Conflict-ignore preserves sent/received/cancelled states on concurrent retries.
        client.table("smartbuy_document_requests").upsert(rows,
            on_conflict="property_id,document_type,requested_from", ignore_duplicates=True).execute()
    return {"candidate_count": len(rows), "delivery_status": "not_sent"}


def acquisition_source(document_type, prop):
    """Assisted official-source routing; never represents an executed lookup."""
    city = str(prop.get("city") or prop.get("comune") or "").strip().casefold()
    province = str(prop.get("province") or prop.get("provincia") or "").strip().upper()
    region = PROVINCE_REGION.get(province)
    values = {"Comune": prop.get("comune_catastale") or prop.get("city") or prop.get("comune"),
              "Foglio": prop.get("foglio"), "Particella": prop.get("particella") or prop.get("mappale"),
              "Subalterno": prop.get("subalterno"), "Codice APE": prop.get("ape_code")}
    data = {k: str(v) for k, v in values.items() if v is not None and str(v).strip()}
    result = {"label": "Richiesta al referente", "url": None, "mode": "request",
              "search_data": data, "missing_inputs": [],
              "note": "Prepara la richiesta e carica il documento ricevuto nel fascicolo."}
    if document_type == "ape":
        if region in _APE_REGIONAL_URL or (province in {"BO", "FE", "FC", "MO", "PR", "PC", "RA", "RE", "RN"} or city == "bologna"):
            region = region or "ER"
            result.update(label=f"{APE_REGISTRY[region]['name']} · registro regionale", url=_APE_REGIONAL_URL[region], mode="assisted",
                          note="Consulta il registro; il risultato della ricerca non equivale al documento completo né a una verifica già eseguita.")
            if not data.get("Codice APE"):
                result["missing_inputs"] = [k for k in ("Comune", "Foglio", "Particella", "Subalterno") if k not in data]
        else:
            result["note"] = "Richiedi l’APE al proprietario. Nessun registro regionale collegato per questa provincia."
    elif document_type in {"visura_catastale", "ispezione_ipotecaria"}:
        if openapi_catasto.configured():
            has_delega = bool(prop.get("delega_confirmed_at"))
            result.update(label="Dati diretti da Catasto e Conservatoria (Openapi)", url=None, mode="in_app",
                          note=("Conferma prima la delega, poi acquistalo con un clic dal pannello "
                                "\"Dati diretti da Catasto e Conservatoria\", qui sopra." if not has_delega else
                                "Acquistalo con un clic dal pannello \"Dati diretti da Catasto e Conservatoria\", "
                                "qui sopra: la delega è già confermata."))
        else:
            result.update(label="Agenzia delle Entrate · SISTER", url="https://sister.agenziaentrate.gov.it/", mode="assisted",
                          note="Accesso professionale abilitato; verificare delega e disponibilità del servizio. Nessuna consultazione è stata eseguita da SmartBuy.")
        result["missing_inputs"] = [k for k in ("Comune", "Foglio", "Particella", "Subalterno") if k not in data]
    elif document_type == "planimetria_catastale":
        sent = prop.get("planimetria_delega_sent_at")
        result.update(label="Delega planimetria (Mod. 12T-AgIm)", url=None, mode="in_app",
                      note=("Delega già segnata come inviata: quando l’Agenzia la rende disponibile nella tua area "
                            "riservata, carica qui il file." if sent else
                            "Scarica il modulo 12T precompilato dal pannello Catasto qui sopra, fallo firmare al "
                            "proprietario e invialo all’Agenzia delle Entrate."))
    elif document_type == "elaborato_planimetrico":
        result.update(label="Agenzia delle Entrate · SISTER", url="https://sister.agenziaentrate.gov.it/", mode="assisted",
                      note="Accesso professionale abilitato; verificare delega e disponibilità del servizio. Nessuna consultazione è stata eseguita da SmartBuy.")
        result["missing_inputs"] = [k for k in ("Comune", "Foglio", "Particella", "Subalterno") if k not in data]
    elif document_type in {"titoli_edilizi", "agibilita"} and city == "bologna":
        result.update(label="Comune di Bologna · Sportello edilizia", url="https://scrivaniadelprofessionista.comune.bologna.it/Sportello/", mode="assisted",
                      note="Avvia l’accesso agli atti con i titoli e le deleghe richiesti dal Comune.")
    elif document_type == "visura_camerale":
        result.update(label="Registro Imprese · visura camerale online", url="https://www.registroimprese.it/", mode="assisted",
                      note="Cerca l’azienda per ragione sociale o P.IVA: visura scaricabile online a pagamento (pochi euro), consegna in pochi minuti.")
    return result
