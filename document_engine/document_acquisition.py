"""Document acquisition rules. Requests are drafts, never outbound messages."""
from collections import defaultdict
from core.operational_models import DocumentRequest

# Operational catalogue, not a declaration of legal obligations.
CATALOGUE = [
    ("ape", "APE completo", "seller", "energy", None, ("ape_energy_certificate",)),
    ("visura_catastale", "Visura catastale", "professional", "cadastral", None, ("visura",)),
    ("planimetria_catastale", "Planimetria catastale", "seller", "cadastral", None, ("planimetria",)),
    ("elaborato_planimetrico", "Elaborato planimetrico", "professional", "cadastral", "sale", ()),
    ("ispezione_ipotecaria", "Ispezione ipotecaria", "professional", "cadastral", "sale", ("visura_ipotecaria",)),
    ("atto_provenienza", "Atto di provenienza", "seller", "ownership", None, ("atto_compravendita", "atto_proprieta")),
    ("titoli_edilizi", "Titoli edilizi e varianti disponibili", "seller", "planning", "sale", ("permesso_costruire",)),
    ("agibilita", "Documentazione di agibilità disponibile", "seller", "planning", "sale", ()),
    ("regolamento_condominiale", "Regolamento condominiale", "administrator", "condominium", "condominium", ()),
    ("verbali_assembleari", "Ultimi verbali assembleari", "administrator", "condominium", "condominium", ()),
    ("consuntivo_condominiale", "Ultimo consuntivo", "administrator", "condominium", "condominium", ()),
    ("preventivo_condominiale", "Preventivo condominiale", "administrator", "condominium", "condominium", ()),
    ("dichiarazione_spese_liti", "Situazione spese, lavori deliberati e liti", "administrator", "condominium", "condominium", ()),
    ("documentazione_impianti", "Documentazione impianti disponibile", "seller", "systems", None, ()),
    ("libretto_impianto", "Libretto impianto", "seller", "systems", "heating", ()),
    ("contratto_locazione", "Contratto di locazione in essere", "seller", "tenancy", "occupied", ()),
    ("ricevuta_rli", "Ricevuta registrazione contratto", "seller", "tenancy", "occupied", ("rli",)),
    ("successione", "Documentazione della successione", "seller", "ownership", "inheritance", ()),
    ("donazione", "Atto di donazione", "seller", "ownership", "donation", ()),
    ("procura", "Procura", "seller", "ownership", "proxy", ()),
    ("visura_camerale", "Visura camerale e poteri di firma", "professional", "ownership", "company", ()),
]


def canonical_type(value):
    value = str(value or "").strip().casefold().replace(" ", "_")
    for key, _, _, _, _, aliases in CATALOGUE:
        if value == key or value in aliases:
            return key
    return value


def build_document_packages(property_record, documents, existing_requests):
    purpose = property_record.get("purpose") or property_record.get("transaction_type")
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
    for key, title, recipient, package, condition, _ in CATALOGUE:
        if condition and conditions[condition] is not True:
            if conditions[condition] is None or (condition == "sale" and not purpose):
                checks.append({"document_type": key, "condition": condition})
            continue
        previous = existing.get(key)
        status = "present" if key in present else (previous["status"] if previous else "draft")
        packages[recipient].append({"document_type": key, "title": title, "package": package,
            "status": status, "request_id": previous.get("request_id") if previous else None,
            "source": acquisition_source(key, property_record)})
    groups = []
    for recipient, items in packages.items():
        missing = [i for i in items if i["status"] in {"draft", "open"}]
        groups.append({"recipient_role": recipient, "items": items,
            "draft_message": "Documenti richiesti per la pratica: \n" + "\n".join("- " + i["title"] for i in missing) if missing else None})
    return {"property_id": property_record["id"], "packages": groups,
            "applicability_checks": checks, "delivery_status": "not_sent"}


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
    values = {"Comune": prop.get("comune_catastale") or prop.get("city") or prop.get("comune"),
              "Foglio": prop.get("foglio"), "Particella": prop.get("particella") or prop.get("mappale"),
              "Subalterno": prop.get("subalterno"), "Codice APE": prop.get("ape_code")}
    data = {k: str(v) for k, v in values.items() if v is not None and str(v).strip()}
    result = {"label": "Richiesta al referente", "url": None, "mode": "request",
              "search_data": data, "missing_inputs": [],
              "note": "Prepara la richiesta e carica il documento ricevuto nel fascicolo."}
    if document_type == "ape":
        if province in {"BO", "FE", "FC", "MO", "PR", "PC", "RA", "RE", "RN"} or city == "bologna":
            result.update(label="SACE · Emilia-Romagna", url="https://sace-er.regione.emilia-romagna.it/ui/ape/public-registry", mode="assisted",
                          note="Consulta il registro; il risultato della ricerca non equivale al documento completo né a una verifica già eseguita.")
            if not data.get("Codice APE"):
                result["missing_inputs"] = [k for k in ("Comune", "Foglio", "Particella", "Subalterno") if k not in data]
        else:
            result["note"] = "Richiedi l’APE al proprietario. Il portale regionale va confermato per questa località."
    elif document_type in {"visura_catastale", "planimetria_catastale", "elaborato_planimetrico", "ispezione_ipotecaria"}:
        result.update(label="Agenzia delle Entrate · SISTER", url="https://sister.agenziaentrate.gov.it/", mode="assisted",
                      note="Accesso professionale abilitato; verificare delega e disponibilità del servizio. Nessuna consultazione è stata eseguita da SmartBuy.")
        result["missing_inputs"] = [k for k in ("Comune", "Foglio", "Particella", "Subalterno") if k not in data]
    elif document_type in {"titoli_edilizi", "agibilita"} and city == "bologna":
        result.update(label="Comune di Bologna · Sportello edilizia", url="https://scrivaniadelprofessionista.comune.bologna.it/Sportello/", mode="assisted",
                      note="Avvia l’accesso agli atti con i titoli e le deleghe richiesti dal Comune.")
    return result
