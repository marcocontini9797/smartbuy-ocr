"""Draft requests an agent sends out by hand to collect documents that have
no API: cadastral records, condo records, notary due diligence. Adapted from
a standalone prototype (property_agent/generators/*.py) that generated these
same three drafts and wrote them to the `tasks` table but was never wired
into the site - the 96 rows it already produced are real and are surfaced
here, not regenerated.

Each generator is a pure function: property fields in, Italian draft text
out. Nothing here sends anything; the agent copies the text and sends it
through their own email/portal, same as the existing document_acquisition
flows that stop at "here is where to go" rather than acting on the agent's
behalf.
"""

from __future__ import annotations

from typing import Any

TASK_TYPES = ("cadastral_request", "condo_email", "notary_request")

# cadastral_request and condo_email cover the same ground as the "professional"
# and "administrator" packages document_acquisition.py already builds for
# AcquisitionWorkflow (typology-aware, with per-document sent/received status);
# only notary_request has no equivalent there, so it is the only type the
# "generate" endpoint below creates going forward. All three remain listed and
# editable, since real historical rows of every type already exist.
GENERATABLE_TASK_TYPES = ("notary_request",)

TASK_LABELS = {
    "cadastral_request": "Richiesta visura catastale",
    "condo_email": "Email all'amministratore di condominio",
    "notary_request": "Richiesta di verifica al notaio",
}


def generate_cadastral_request(property_record: dict[str, Any]) -> str:
    address = property_record.get("address") or "N/D"
    city = property_record.get("city") or "N/D"
    return f"""=== RICHIESTA VISURA CATASTALE ===

Proprieta': {address}, {city}

ISTRUZIONI PER L'OTTENIMENTO DELLA VISURA CATASTALE:

1. Accedere al portale dell'Agenzia delle Entrate:
   https://pratiche.agenziaentrate.gov.it/

2. Autenticarsi con SPID o CIE.

3. Selezionare "Servizi Catasto" -> "Richiesta Visura Catastale".

4. Inserire i dati catastali (se disponibili):
   - Foglio:
   - Particella:
   - Subalterno:
   - Comune: {city}

5. Effettuare il pagamento del diritto di segreteria (circa 25 euro).

6. La visura sara' disponibile per download immediato.

NOTA:
- La visura catastale gratuita e' disponibile presso gli Uffici
  Provinciali dell'Agenzia delle Entrate (sportello).
- Per la planimetria catastale e' necessaria una richiesta separata
  con costo aggiuntivo (circa 15 euro) - se l'immobile ha gia' una
  delega attiva, usa il flow "Planimetria" nella scheda documenti
  invece di questa procedura manuale.

DOCUMENTI RICHIESTI:
- Documento di identita' valido
- Codice fiscale
- Dati catastali dell'immobile""".strip()


def generate_condo_email(property_record: dict[str, Any]) -> str:
    address = property_record.get("address") or "N/D"
    city = property_record.get("city") or "N/D"
    owner_name = property_record.get("owner_name") or "Il/La Proprietario/a"
    admin_name = property_record.get("admin_name") or "Amministratore di Condominio"
    return f"""Oggetto: Richiesta Documentazione Condominiale - {address}, {city}

Gentile {admin_name},

mi chiamo {owner_name} e sono proprietario/a di un immobile sito in
{address}, {city}.

Vi scrivo per richiedere la seguente documentazione condominiale:

1. Verbali delle ultime 3 assemblee condominiali
2. Relazione consuntiva e preventiva spese
3. Regolamento condominiale (ultima versione)
4. Stato patrimoniale del condominio
5. Eventuali liti o contenziosi in corso
6. Asseverazione dell'amministratore ex art. 1130 c.c.
7. Ultima bolletta/gestione ordinaria e straordinaria

Vi sarei grato/a se poteste inviarmi la documentazione preferibilmente
in formato digitale (PDF) all'indirizzo e-mail indicato.

Resto a disposizione per eventuali chiarimenti.

Cordiali saluti,

{owner_name}""".strip()


def generate_notary_request(property_record: dict[str, Any]) -> str:
    address = property_record.get("address") or "N/D"
    city = property_record.get("city") or "N/D"
    owner_name = property_record.get("owner_name") or "Il/La Proprietario/a"
    asking_price = property_record.get("asking_price")
    price_str = f"EUR {asking_price:,.0f}".replace(",", ".") if asking_price else "N/D"
    return f"""RICHIESTA DI VERIFICA LEGALE IMMOBILIARE

Spett.le Notaio,

Il/La sottoscritto/a {owner_name}, con domicilio in {address}, {city},
desidera procedere all'acquisto di un immobile sito in {address}, {city},
al prezzo di {price_str}.

Si chiede cortesemente di voler effettuare le seguenti verifiche:

1. VERIFICA DELLA PROPRIETA'
   - Catena dei passaggi di proprieta' (ultimi 20 anni)
   - Titolo di proprieta' del venditore

2. VERIFICA DEI PESI E VINCOLI
   - Iscrizioni ipotecarie
   - Domande giudiziali
   - Deleghe di pagamento

3. VERIFICA URBANISTICO-EDILIZIA
   - Conformita' catastale
   - Conformita' urbanistica
   - Permessi di costruire e agibilita'

4. VERIFICA CONDOMINIALE
   - Oneri condominiali non pagati
   - Liti condominiali in corso

5. CERTIFICATI E DICHIARAZIONI
   - Certificato di Destinazione Urbanistica (se necessario)
   - Certificato energetico (APE)

Si prega di comunicare il costo della pratica e i tempi stimati.

Resto a disposizione per ulteriori informazioni.

Distinti saluti,

{owner_name}
Indirizzo: {address}, {city}""".strip()


_GENERATORS = {
    "cadastral_request": generate_cadastral_request,
    "condo_email": generate_condo_email,
    "notary_request": generate_notary_request,
}


def generate_task_content(task_type: str, property_record: dict[str, Any]) -> str:
    return _GENERATORS[task_type](property_record)
