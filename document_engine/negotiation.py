"""Negotiation brief for the buyer, derived from the sale checklist.

Deterministic playbook, no LLM: for every missing document and every issue it
returns what to ask the seller, which conditions to put in the offer or in
the preliminary contract, what can weigh on the price and what the notary
will check. Wording is practical guidance, not legal advice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Play:
    questions: tuple[str, ...] = ()
    clauses: tuple[str, ...] = ()
    price: tuple[str, ...] = ()
    notary: tuple[str, ...] = ()


# When a document is missing.
MISSING: dict[str, Play] = {
    "visura_catastale": Play(
        questions=("Può fornire una visura catastale aggiornata?",),
        notary=("Controlla intestazione e dati catastali dell'immobile.",)),
    "planimetria": Play(
        questions=("La planimetria catastale corrisponde allo stato attuale dell'immobile?",),
        clauses=("Il venditore garantisce la conformità catastale e aggiorna a sue spese la planimetria, se necessario, prima del rogito.",),
        notary=("Riceve la dichiarazione di conformità catastale da inserire nell'atto.",)),
    "ape": Play(
        questions=("È disponibile un APE valido? Se è scaduto, chi lo rifà?",),
        clauses=("Il venditore consegna un APE valido prima del rogito, a sue spese.",)),
    "visura_ipotecaria": Play(
        questions=("Sull'immobile ci sono mutui, ipoteche o pignoramenti?",),
        clauses=("L'immobile sarà libero da ipoteche, pignoramenti e trascrizioni pregiudizievoli al rogito; "
                 "eventuali ipoteche sono cancellate a cura e spese del venditore.",),
        notary=("Esegue le ispezioni ipotecarie aggiornate prima del rogito.",)),
    "atto_di_provenienza": Play(
        questions=("Come è diventato proprietario: acquisto, donazione o successione? Può fornire l'atto?",),
        notary=("Verifica la catena delle provenienze degli ultimi vent'anni.",)),
    "titolo_edilizio": Play(
        questions=("Sono stati fatti lavori o modifiche interne? Con quali pratiche edilizie?",),
        clauses=("Il venditore garantisce la regolarità urbanistica ed edilizia; eventuali sanatorie sono a suo carico prima del rogito.",),
        price=("Se emergono difformità da sanare, tempi e costi della sanatoria incidono sul prezzo.",),
        notary=("Riporta in atto gli estremi dei titoli edilizi dichiarati dal venditore.",)),
    "certificato_agibilita": Play(
        questions=("L'immobile ha il certificato di agibilità (o la segnalazione certificata)?",)),
    "dichiarazione_conformita_impianti": Play(
        questions=("Gli impianti hanno la dichiarazione di conformità? Quando sono stati rifatti?",),
        price=("Impianti da adeguare: il costo dei lavori è un argomento di trattativa.",)),
    "relazione_tecnica_integrata": Play(
        clauses=("Far redigere una relazione tecnica integrata prima del preliminare, o prevederla come condizione.",)),
    "regolamento_condominio": Play(
        questions=("Il regolamento di condominio pone limiti d'uso (animali, affitti brevi, attività)?",)),
    "contratto_locazione": Play(
        questions=("Il locale è affittato? A chi, con quale canone e fino a quando? Il contratto è registrato?",),
        clauses=("Se il locale è locato: il venditore consegna contratto e ricevute di registrazione e dichiara canoni e morosità.",)),
    "verbale_assemblea_condominio": Play(
        questions=("Ci sono lavori straordinari deliberati o in programma? Ci sono spese condominiali arretrate?",),
        clauses=("Le spese straordinarie deliberate prima del rogito restano a carico del venditore.",),
        price=("Lavori condominiali imminenti a carico dell'acquirente vanno considerati nel prezzo.",)),
}

# When a document is present but has an issue: by red-flag category or
# cross-validation field (prefix match).
ISSUES: dict[str, Play] = {
    "formalita_pregiudizievoli": Play(
        questions=("Qual è l'importo residuo del mutuo o del debito? Come e quando verrà cancellata la formalità?",),
        clauses=("Cancellazione di ipoteche e formalità contestuale al rogito, con assenso del creditore, a cura del venditore.",),
        notary=("Verifica l'estinzione del debito e la cancellazione delle formalità.",)),
    "provenienza": Play(
        questions=("Chi sono gli eredi o i legittimari del donante o del defunto? Sono disposti a rinunciare?",),
        clauses=("A carico del venditore: polizza 'donazione sicura' o rinuncia dei legittimari, se praticabile.",),
        price=("Provenienza da donazione recente: alcune banche negano il mutuo, il che riduce gli acquirenti possibili.",),
        notary=("Valuta i rischi della provenienza (azione di riduzione, successione non trascritta).",)),
    "conformita_catastale": Play(
        clauses=("Aggiornamento catastale a cura e spese del venditore prima del rogito.",),
        price=("Costi di aggiornamento catastale e di eventuale regolarizzazione.",)),
    "conformita_urbanistica": Play(
        clauses=("Sanatoria delle difformità a carico del venditore prima del rogito, o condizione sospensiva.",),
        price=("Difformità urbanistiche: costi, tempi e rischio di non sanabilità pesano sul prezzo.",)),
    "conformita_tecnica": Play(
        clauses=("Regolarizzazione delle difformità segnalate dal tecnico prima del rogito.",),
        price=("Le difformità rilevate dal tecnico hanno un costo di regolarizzazione.",)),
    "agibilita": Play(
        price=("Assenza di agibilità: può rendere più difficile il mutuo e la rivendita.",)),
    "conformita_impianti": Play(
        price=("Impianti non conformi: costi di adeguamento da considerare.",)),
    "ape": Play(clauses=("Nuovo APE a carico del venditore prima del rogito.",)),
    "ape.scadenza": Play(clauses=("Nuovo APE a carico del venditore prima del rogito.",)),
    "visura.data": Play(questions=("Può fornire una visura aggiornata (meno di 3 mesi)?",)),
    "condominio": Play(
        questions=("Qual è l'importo delle spese straordinarie e delle eventuali morosità?",),
        clauses=("Spese straordinarie deliberate e arretrati condominiali a carico del venditore.",),
        price=("Spese condominiali straordinarie o arretrate incidono sul costo totale.",)),
    "locazione": Play(
        questions=("L'immobile è locato? Il contratto è registrato? Quando scade?",
                   "Se l'uso è commerciale: il conduttore è stato informato del suo diritto di prelazione?"),
        clauses=("Immobile libero da persone e cose alla data del rogito, oppure subentro nel contratto con canoni e cauzione indicati.",
                 "Per locazioni commerciali: comunicazione al conduttore per la prelazione (art. 38 L. 392/1978) prima del rogito, a cura del venditore."),
        price=("Un locale affittato si valuta sul canone e sulla durata residua; il rischio di riscatto del conduttore va considerato.",)),
    "categoria_catastale": Play(
        questions=("La destinazione d'uso legittima del locale corrisponde a quella catastale?",),
        clauses=("Eventuale cambio di destinazione d'uso o di categoria a cura e spese del venditore prima del rogito.",),
        price=("Una destinazione d'uso non coerente può limitare l'utilizzo e il valore dell'immobile.",)),
    "vincoli": Play(
        questions=("Su quali vincoli insiste l'immobile (paesaggistici, storico-artistici)?",),
        notary=("Verifica eventuali diritti di prelazione dello Stato o di enti.",)),
    "coerenza_documentale": Play(questions=("Può chiarire le differenze tra i documenti forniti?",)),
    "proprietari": Play(
        questions=("Chi sono esattamente tutti i proprietari? Firmeranno tutti la proposta e l'atto?",),
        clauses=("Alla proposta e al rogito intervengono tutti i proprietari risultanti dai documenti.",),
        notary=("Verifica la titolarità e i poteri di firma dei venditori.",)),
    "quota_proprieta": Play(questions=("Le quote di proprietà sommano all'intero? Chi possiede le altre quote?",)),
    "codice_fiscale": Play(questions=("Può fornire documento d'identità e codice fiscale dei proprietari?",)),
    "catasto.": Play(
        questions=("Può chiarire i dati catastali: i documenti riportano valori diversi?",),
        notary=("Allinea in atto i dati catastali corretti.",)),
    "superficie": Play(
        questions=("Qual è la superficie commerciale reale? Da quale documento è ricavata?",),
        price=("Superficie da verificare: il prezzo al metro quadro va ricalcolato su quella reale.",)),
    "prezzo_eur": Play(questions=("Quale prezzo è quello concordato? I documenti riportano importi diversi.",)),
    "indirizzo": Play(questions=("L'indirizzo dei documenti corrisponde all'immobile in vendita?",)),
}

GENERAL_CLAUSES = (
    "Se serve un mutuo: proposta condizionata alla sua concessione entro una data precisa.",
    "Caparra versata al notaio o su conto dedicato, non direttamente al venditore.",
)


@dataclass
class _Entry:
    text: str
    reasons: list[str] = field(default_factory=list)


def _issue_play(category: str) -> Play | None:
    if category in ISSUES:
        return ISSUES[category]
    # Prefix match for families of fields, e.g. "catasto.foglio", "superficie.rapporto".
    return next((play for key, play in ISSUES.items() if category.startswith(key)), None)


def build_negotiation_brief(checklist: dict[str, Any]) -> dict[str, Any]:
    sections: dict[str, dict[str, _Entry]] = {name: {} for name in ("questions", "clauses", "price", "notary")}
    blockers: list[dict[str, Any]] = []

    def add(play: Play, reason: str) -> None:
        for name in sections:
            for text in getattr(play, name):
                entry = sections[name].setdefault(text, _Entry(text))
                if reason not in entry.reasons:
                    entry.reasons.append(reason)

    for item in checklist.get("items", []):
        if not item.get("applicable", True):
            continue
        if item["status"] == "missing" and item["key"] in MISSING:
            add(MISSING[item["key"]], f"{item['title']}: mancante")
        for issue in item.get("issues", []):
            play = _issue_play(str(issue.get("category") or ""))
            if play:
                add(play, f"{item['title']}: {issue['title']}")
            if issue.get("severity") == "critica":
                blockers.append({"title": issue["title"], "document": item["title"], "action": issue.get("action")})
    for issue in checklist.get("general_issues", []):
        play = _issue_play(str(issue.get("category") or ""))
        if play:
            add(play, issue["title"])
        if issue.get("severity") == "critica":
            blockers.append({"title": issue["title"], "document": None, "action": issue.get("action")})

    def listing(name: str) -> list[dict[str, Any]]:
        return [{"text": e.text, "reasons": e.reasons} for e in sections[name].values()]

    return {
        "blockers": blockers,
        "questions": listing("questions"),
        "clauses": listing("clauses") + [{"text": text, "reasons": ["Buona prassi"]} for text in GENERAL_CLAUSES],
        "price_levers": listing("price"),
        "notary_checks": listing("notary"),
        "note": "Indicazioni pratiche per preparare la trattativa, non consulenza legale: "
                "proposta e preliminare vanno rivisti con il notaio o un professionista.",
    }
