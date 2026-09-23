"""Deterministic knowledge about what an agent needs for each property flow."""

from __future__ import annotations

from core.property_flow_models import (
    PlaybookRequirement,
    PropertyFlowPlaybook,
    PropertyPurpose,
    RequirementLevel,
    WorkflowStage,
)


COMMON = [
    PlaybookRequirement(
        requirement_id="common.identity",
        domain="property",
        title="Identità univoca dell'immobile",
        why_it_matters="Evita di collegare documenti, controlli o annunci all'unità sbagliata.",
        level=RequirementLevel.MANDATORY,
        legal_note="Necessaria per identificare correttamente il bene nel contratto e negli adempimenti.",
        expected_documents=["visura catastale", "planimetria catastale"],
        blocking=True,
    ),
    PlaybookRequirement(
        requirement_id="common.authority",
        domain="ownership",
        title="Titolarità e potere di firma",
        why_it_matters="L'agente deve sapere chi può conferire l'incarico e sottoscrivere il contratto.",
        level=RequirementLevel.MANDATORY,
        legal_note="Il contratto deve essere sottoscritto dal titolare o da un soggetto validamente autorizzato.",
        expected_documents=["documento di identità", "titolo di proprietà", "eventuale procura"],
        blocking=True,
        professional_review="notaio o legale nei casi dubbi",
    ),
    PlaybookRequirement(
        requirement_id="common.ape",
        domain="energy",
        title="Prestazione energetica",
        why_it_matters="Alimenta annuncio, informativa al cliente e documentazione contrattuale.",
        level=RequirementLevel.MANDATORY,
        legal_note="Obbligatoria nei casi previsti dalla disciplina energetica, salvo specifiche esclusioni.",
        expected_documents=["APE in corso di validità"],
    ),
]


SALE = [
    PlaybookRequirement(
        requirement_id="sale.provenance",
        domain="ownership",
        title="Provenienza e continuità delle intestazioni",
        why_it_matters="Conferma come il venditore ha acquisito l'immobile e segnala successioni, donazioni o disallineamenti.",
        level=RequirementLevel.MANDATORY,
        legal_note="La titolarità e la continuità devono essere verificate per il trasferimento.",
        expected_documents=["atto di provenienza", "successione o donazione se presenti"],
        blocking=True,
        professional_review="notaio",
    ),
    PlaybookRequirement(
        requirement_id="sale.cadastral_conformity",
        domain="cadastral",
        title="Coerenza catastale e planimetrica",
        why_it_matters="Dati catastali, intestazioni, consistenza e planimetria devono essere riconciliati con lo stato rilevato.",
        level=RequirementLevel.MANDATORY,
        legal_note="L'atto di vendita deve contenere i riferimenti catastali e la dichiarazione o attestazione di conformità prevista.",
        expected_documents=["visura catastale attuale", "planimetria catastale", "rilievo o attestazione tecnica"],
        blocking=True,
        professional_review="tecnico abilitato",
    ),
    PlaybookRequirement(
        requirement_id="sale.urbanistic_conformity",
        domain="urbanistic",
        title="Titoli edilizi e stato urbanistico",
        why_it_matters="Individua opere non documentate, pratiche aperte, sanatorie e verifiche necessarie prima dell'offerta.",
        level=RequirementLevel.MANDATORY,
        legal_note="Gli estremi urbanistico-edilizi richiesti devono risultare nell'atto; la relazione tecnica completa è altamente consigliata.",
        expected_documents=["titoli edilizi", "agibilità se disponibile", "pratiche edilizie successive"],
        blocking=True,
        professional_review="tecnico abilitato",
    ),
    PlaybookRequirement(
        requirement_id="sale.encumbrances",
        domain="mortgage",
        title="Ipoteca, pignoramenti, servitù e vincoli",
        why_it_matters="Incide sulla trasferibilità e sulle condizioni da inserire nella proposta o nel preliminare.",
        level=RequirementLevel.MANDATORY,
        legal_note="Le formalità pregiudizievoli devono essere verificate nel percorso notarile.",
        expected_documents=["ispezione ipotecaria", "note di trascrizione rilevanti"],
        blocking=True,
        professional_review="notaio",
    ),
    PlaybookRequirement(
        requirement_id="sale.condominium",
        domain="condominium",
        title="Situazione condominiale",
        why_it_matters="L'agente deve evidenziare spese, arretrati, lavori deliberati e controversie note.",
        level=RequirementLevel.HIGHLY_RECOMMENDED,
        legal_note="La raccolta completa prima dell'offerta riduce contestazioni su arretrati e lavori deliberati.",
        expected_documents=["regolamento", "ultimi verbali", "consuntivo", "preventivo", "dichiarazione amministratore"],
    ),
    PlaybookRequirement(
        requirement_id="sale.occupancy",
        domain="occupancy",
        title="Disponibilità e occupazione",
        why_it_matters="Chiarisce se l'immobile è libero, locato o occupato e quando potrà essere consegnato.",
        level=RequirementLevel.MANDATORY,
        legal_note="La situazione di occupazione deve essere rappresentata correttamente negli accordi.",
        expected_documents=["contratto di locazione se presente", "accordi di rilascio"],
        blocking=True,
    ),
    PlaybookRequirement(
        requirement_id="sale.technical_report",
        domain="urbanistic",
        title="Relazione tecnica integrata",
        why_it_matters="Riunisce in un controllo professionale la coerenza catastale, edilizia e dello stato dei luoghi.",
        level=RequirementLevel.HIGHLY_RECOMMENDED,
        legal_note="Non è un obbligo uniforme su tutto il territorio, ma riduce fortemente il rischio prima della proposta.",
        expected_documents=["relazione tecnica integrata o relazione di conformità"],
        professional_review="tecnico abilitato",
    ),
    PlaybookRequirement(
        requirement_id="sale.systems",
        domain="systems",
        title="Documentazione degli impianti",
        why_it_matters="Permette di rappresentare correttamente stato, manutenzioni e documentazione disponibile.",
        level=RequirementLevel.HIGHLY_RECOMMENDED,
        legal_note="Verificare gli obblighi applicabili in base a epoca, lavori eseguiti e contenuto del contratto.",
        expected_documents=["dichiarazioni di conformità o rispondenza disponibili", "libretto impianto"],
        professional_review="tecnico competente se emergono dubbi",
    ),
]


RENT_COMMON = [
    PlaybookRequirement(
        requirement_id="rent.contract",
        domain="rental",
        title="Tipo, durata e condizioni del contratto",
        why_it_matters="Determina canone, durata, recesso, aggiornamenti, garanzie e adempimenti.",
        level=RequirementLevel.MANDATORY,
        legal_note="Forma e contenuti devono rispettare il tipo di locazione scelto.",
        expected_documents=["bozza contratto", "eventuale accordo territoriale"],
        blocking=True,
        professional_review="consulente o associazione di categoria per regimi particolari",
    ),
    PlaybookRequirement(
        requirement_id="rent.costs",
        domain="financial",
        title="Canone, deposito e spese",
        why_it_matters="Evita ambiguità su importi, scadenze, oneri accessori, utenze e deposito.",
        level=RequirementLevel.MANDATORY,
        legal_note="Canone e condizioni economiche devono essere definiti; il deposito è facoltativo ma, se previsto, va regolato.",
        expected_documents=["prospetto canone e spese", "ultimo consuntivo condominiale"],
        blocking=True,
    ),
    PlaybookRequirement(
        requirement_id="rent.condition",
        domain="property",
        title="Stato, dotazioni e consegna",
        why_it_matters="Serve a documentare ciò che viene consegnato e riduce contestazioni alla riconsegna.",
        level=RequirementLevel.HIGHLY_RECOMMENDED,
        legal_note="Verbale, inventario e fotografie sono prove operative molto utili, soprattutto per immobili arredati.",
        expected_documents=["verbale di consegna", "inventario", "fotografie", "letture contatori"],
    ),
    PlaybookRequirement(
        requirement_id="rent.registration",
        domain="compliance",
        title="Registrazione e adempimenti successivi",
        why_it_matters="SmartBuy deve controllare registrazione, proroghe, cessioni, subentri e risoluzioni.",
        level=RequirementLevel.MANDATORY,
        legal_note="Obbligatoria per i contratti soggetti a registrazione; sono esclusi i casi che non superano complessivamente 30 giorni nell'anno.",
        expected_documents=["modello RLI", "ricevuta di registrazione"],
        blocking=True,
    ),
    PlaybookRequirement(
        requirement_id="rent.tenant_assessment",
        domain="tenant",
        title="Sostenibilità e garanzie del conduttore",
        why_it_matters="Aiuta l'agente a valutare la sostenibilità del canone e a concordare garanzie proporzionate.",
        level=RequirementLevel.HIGHLY_RECOMMENDED,
        legal_note="Raccogliere solo dati pertinenti, con informativa e trattamento conforme alla privacy.",
        expected_documents=["documenti reddituali pertinenti", "eventuale garanzia o garante"],
    ),
    PlaybookRequirement(
        requirement_id="rent.condominium_rules",
        domain="condominium",
        title="Regole condominiali e ripartizione delle spese",
        why_it_matters="Riduce contestazioni su uso dell'immobile, animali, parti comuni e oneri accessori.",
        level=RequirementLevel.HIGHLY_RECOMMENDED,
        expected_documents=["regolamento condominiale", "prospetto spese locatore-conduttore"],
    ),
    PlaybookRequirement(
        requirement_id="rent.maintenance",
        domain="property",
        title="Manutenzioni, guasti e assicurazione",
        why_it_matters="Definisce referenti, stato iniziale, interventi aperti e coperture utili.",
        level=RequirementLevel.HIGHLY_RECOMMENDED,
        expected_documents=["registro manutenzioni disponibile", "eventuale polizza", "contatti assistenza"],
    ),
]


SHORT_TERM = [
    PlaybookRequirement(
        requirement_id="short_rent.cin",
        domain="short_rental",
        title="CIN e codici territoriali",
        why_it_matters="Il codice deve essere verificato e riportato dove richiesto per l'offerta dell'unità.",
        level=RequirementLevel.MANDATORY,
        legal_note="Obbligatorio per locazioni brevi o turistiche; restano applicabili eventuali codici territoriali.",
        expected_documents=["CIN", "eventuale codice regionale o comunale"],
        blocking=True,
    ),
    PlaybookRequirement(
        requirement_id="short_rent.safety",
        domain="safety",
        title="Dotazioni di sicurezza",
        why_it_matters="Verifica la presenza documentata delle dotazioni richieste per la locazione breve o turistica.",
        level=RequirementLevel.MANDATORY,
        legal_note="Applicare i requisiti nazionali vigenti e verificare eventuali prescrizioni ulteriori.",
        expected_documents=["dichiarazione dotazioni", "manutenzioni o certificazioni disponibili"],
        blocking=True,
        professional_review="tecnico competente per requisiti impiantistici",
    ),
    PlaybookRequirement(
        requirement_id="short_rent.local_rules",
        domain="compliance",
        title="Obblighi regionali e comunali",
        why_it_matters="Comunicazioni, imposta di soggiorno e requisiti possono variare in base al territorio.",
        level=RequirementLevel.MANDATORY,
        legal_note="Obbligatori quando previsti dalla Regione o dal Comune dell'immobile.",
        expected_documents=["adempimenti regionali", "adempimenti comunali"],
        professional_review="verifica normativa locale aggiornata",
    ),
]


def get_property_playbook(purpose: PropertyPurpose) -> PropertyFlowPlaybook:
    requirements = [item.model_copy(deep=True) for item in COMMON]
    if purpose == PropertyPurpose.SALE:
        requirements.extend(item.model_copy(deep=True) for item in SALE)
        questions = [
            "L'immobile è libero o esiste un contratto di locazione?",
            "Sono state eseguite opere rispetto alla planimetria disponibile?",
            "Esistono lavori condominiali deliberati o arretrati?",
            "La vendita dipende da mutuo, successione, procura o cancellazione di gravami?",
        ]
    else:
        requirements.extend(item.model_copy(deep=True) for item in RENT_COMMON)
        questions = [
            "Quale durata e finalità deve avere la locazione?",
            "L'immobile è arredato e quali dotazioni vengono consegnate?",
            "Quali spese sono incluse nel canone?",
            "Quali garanzie sono richieste al conduttore?",
        ]
        if purpose == PropertyPurpose.RENT_SHORT_TERM:
            requirements.extend(item.model_copy(deep=True) for item in SHORT_TERM)
            questions.extend([
                "Il CIN è già stato attribuito e coincide con l'unità?",
                "Quali obblighi locali si applicano al Comune dell'immobile?",
            ])

    return PropertyFlowPlaybook(
        purpose=purpose,
        stages=list(WorkflowStage),
        requirements=requirements,
        agent_questions=questions,
        output_sections=[
            "stato di pubblicabilità",
            "blocchi prima del contratto",
            "rischi da spiegare al cliente",
            "documenti mancanti",
            "prossime tre azioni",
        ],
    )
