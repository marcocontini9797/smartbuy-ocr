"""Explain deterministic cross-document findings as tasks for the agent.

This is an operational review, never a certificate of conformity or legal advice.
Every action identifies its trigger and distinguishes evidence from missing inputs.
"""
from core.operational_models import stable_id
from document_engine.typology import typology_of, contract_of

VERSION = "1.0"


def build_agent_review(property_id, property_record, documents, findings):
    prop = property_record or {}
    context = prop.get("workflow_context") or {}
    contract = contract_of(prop)
    typology = typology_of(prop)
    types = {d.get("document_type") for d in documents if d.get("processing_status") not in {"failed", "rejected"}}
    actions = []

    def add(key, title, why, action, owner, severity="medium", source_ids=(), finding_ids=()):
        actions.append({"id": stable_id("agent-review",property_id,key), "rule_id":key, "title":title,
                        "why":why, "next_step":action, "assigned_role":owner, "priority":severity,
                        "sources":sorted(set(source_ids)), "finding_ids":sorted(set(finding_ids))})

    groups = {}
    for finding in findings:
        if finding.status not in {"conflict", "invalid", "extraction_unstable", "attention"}:
            continue
        if finding.status == "extraction_unstable" or (finding.status == "attention" and "letture" in (finding.detail or "")):
            domain="reading"
        elif finding.field.startswith("catasto.") or finding.field=="indirizzo": domain="identity"
        elif finding.field in {"proprietari","codici_fiscali","quota_proprieta"}: domain="authority"
        elif finding.field.startswith("superficie"): domain="surface"
        elif finding.field in {"prezzo_eur","canone_mensile_eur"}: domain="economics"
        elif finding.field.startswith("ape.") or finding.field in {"classe_energetica","epgl"}: domain="energy"
        else: domain="other"
        groups.setdefault(domain,[]).append(finding)
    guidance = {
        "reading":("Conferma prima la lettura dei documenti", "Un errore OCR può generare criticità apparenti.", "Apri le fonti originali, correggi i dati incerti e riesegui il confronto.","Agente"),
        "identity":("Verifica che i documenti riguardino la stessa unità", "Dati catastali o indirizzi discordanti possono riferirsi a un’altra unità o a una variazione storica.", "Confronta identificativi completi e date; chiedi al tecnico di ricostruire eventuali variazioni.","Agente e tecnico"),
        "authority":("Chiarisci titolarità e soggetti della pratica", "Un’intestazione catastale o un nome discordante richiede di ricostruire ruoli e provenienza.", "Controlla date e ruoli negli atti, eventuali quote e procure; sottoponi i dubbi al professionista incaricato.","Agente e notaio"),
        "surface":("Chiarisci quale superficie stai utilizzando", "Superficie utile, catastale e commerciale non rappresentano necessariamente la stessa misura.", "Verifica unità, pertinenze e criterio di misura prima di aggiornare annuncio o valutazione.","Agente e tecnico"),
        "economics":("Riconcilia gli importi della pratica", "Importi diversi possono riferirsi a contratti, periodi o componenti differenti.", "Confronta date, oggetto, periodicità e voci incluse prima di presentare l’importo come concordato.","Agente"),
        "energy":("Chiarisci i dati energetici", "Classe o date discordanti possono dipendere da attestati differenti o superati.", "Verifica identificativi dell’unità, data e attestato pertinente con il proprietario o il certificatore.","Agente e certificatore"),
        "other":("Verifica le informazioni discordanti", "Sono presenti punti aperti nelle fonti disponibili.","Controlla le prove indicate e chiedi il documento aggiornato al referente.","Agente"),
    }
    for domain, items in groups.items():
        title,why,step,owner=guidance[domain]
        add(domain,title,why,step,owner,"high" if any(i.severity=="high" for i in items) else "medium",
            [s for i in items for s in i.sources],[i.finding_id for i in items])
    if not documents:
        add("intake","Acquisisci i primi documenti","La pratica non dispone ancora di fonti documentali.","Apri Documenti e recupero e carica i file disponibili.","Agente","high")
    if context.get("occupancy") == "leased" and "contratto_locazione" not in types:
        add("lease","Recupera il contratto di locazione in essere","L’immobile risulta locato, ma manca il contratto nel fascicolo.",
            "Chiedi contratto, registrazione e integrazioni; chiarisci disponibilità e condizioni prima della " + ("vendita." if contract=="vendita" else "nuova locazione."),"Proprietario","high")
    if typology.asset == "commerciale":
        if not str(context.get("intended_use") or "").strip():
            add("intended_use","Definisci l’attività prevista","La sola tipologia del locale non basta per valutare l’uso del futuro occupante.","Compila l’uso previsto in Personalizza il percorso.","Agente","high")
        elif not types & {"titolo_edilizio","titoli_edilizi","relazione_tecnica_integrata"}:
            add("use_documents","Raccogli le fonti sull’uso del locale","L’attività prevista è dichiarata, ma mancano fonti urbanistiche per valutarne la compatibilità.","Recupera i titoli e chiedi al tecnico o al SUAP la verifica per l’attività indicata.","Tecnico / SUAP","high")
    order={key:i for i,key in enumerate(["intake","reading","identity","authority","lease","intended_use","use_documents","energy","surface","economics","other"])}
    actions.sort(key=lambda a:(0 if a["priority"]=="high" else 1,order.get(a["rule_id"],99)))
    return {"version":VERSION,"contract":contract,"typology":typology.key,"actions":actions,
            "next_action":actions[0] if actions else None,
            "assessment":"needs_review" if actions else "no_issues_in_available_checks",
            "note":"Indicazioni basate sui documenti e sulle risposte disponibili. L’assenza di segnalazioni non certifica la regolarità dell’immobile."}
