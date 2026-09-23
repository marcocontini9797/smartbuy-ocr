"""
Consistency engine + missing-info detection.

Questo è il pezzo che sta "sopra" gli schemi (leva 2): una volta che ogni documento
del fascicolo è stato estratto in una struttura tipata, possiamo confrontare
programmaticamente i campi comparabili tra documenti diversi (niente LLM necessario
qui, è logica deterministica su dati già strutturati -> più affidabile ed economico
che chiedere di nuovo al modello "sono coerenti questi due documenti?").

Il missing-info detection genera invece le domande da porre al proprietario quando
mancano dati attesi per completare la due diligence.
"""

from __future__ import annotations

from observability import Identifiable, stable_id

from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel

from schemas import (
    APE,
    AttoCompravendita,
    ContrattoLocazione,
    RiferimentoCatastale,
    VisuraCatastale,
    campi_accessori,
    campi_essenziali,
)


@dataclass
class Discrepancy(Identifiable):
    campo: str
    documento_a: str
    valore_a: str
    documento_b: str
    valore_b: str
    gravita: str  # "bassa" | "media" | "alta"
    dettaglio: str = ""


def _pct_diff(a: float, b: float) -> float:
    if a == 0 and b == 0:
        return 0.0
    return abs(a - b) / max(abs(a), abs(b), 1e-9)


def check_superficie(
    atto: Optional[AttoCompravendita],
    ape: Optional[APE],
    margine_fisiologico: float = 0.35,
    margine_alta_gravita: float = 0.60,
) -> list[Discrepancy]:
    """Confronta la superficie "commerciale" dichiarata nell'atto con la
    superficie "utile" riportata in APE.

    Importante: queste due misure NON sono la stessa grandezza per definizione,
    quindi un confronto ingenuo a soglia fissa produce falsi positivi. La
    superficie commerciale (usata per le quotazioni, criteri OMI/DPR 138/98) è
    calcolata sommando la superficie utile calpestabile a percentuali ridotte di
    pertinenze come balconi, cantine, box (fonte: criteri di misurazione OMI e
    DPR 138/98 sulle unità immobiliari urbane) — per questo è normale che la
    superficie commerciale in atto sia MAGGIORE della superficie utile in APE,
    anche di un buon margine, senza che questo segnali un problema.

    Quello che invece è un segnale utile da controllare:
    - la superficie commerciale è MINORE di quella utile (non dovrebbe succedere,
      perché la commerciale include sempre almeno la utile più eventuali
      pertinenze pesate): gravità alta;
    - il margine tra le due supera una soglia oltre la quale la differenza non è
      più spiegabile da normali pertinenze (balconi/cantine/box) ma suggerisce
      un errore di trascrizione, un immobile diverso, o una difformità reale:
      qui usiamo due soglie indicative (35% e 60%) NON normative — vanno tarate
      sul tipo di immobile (un attico con ampio terrazzo avrà uno scarto
      fisiologico maggiore di un bilocale senza pertinenze).
    """
    if not atto or not ape:
        return []
    sup_atto = atto.superficie_dichiarata_mq
    sup_ape = ape.superficie_utile_mq
    if not sup_atto or not sup_ape or not sup_atto.valore or not sup_ape.valore:
        return []
    try:
        val_atto = float(str(sup_atto.valore).replace(",", ".").split()[0])
        val_ape = float(str(sup_ape.valore).replace(",", ".").split()[0])
    except (ValueError, IndexError):
        return []

    if val_ape <= 0:
        return []

    eccesso_atto_su_ape = (val_atto - val_ape) / val_ape  # >0 = atto maggiore di APE, atteso

    if eccesso_atto_su_ape < 0:
        return [
            Discrepancy(
                campo="superficie_mq",
                documento_a="atto_compravendita",
                valore_a=str(val_atto),
                documento_b="ape",
                valore_b=str(val_ape),
                gravita="alta",
                dettaglio=(
                    "La superficie commerciale in atto è MINORE della superficie utile "
                    "in APE: anomalo, perché la commerciale dovrebbe includere almeno "
                    "la utile più eventuali pertinenze. Verificare che i due documenti "
                    "si riferiscano davvero alla stessa unità immobiliare."
                ),
            )
        ]

    if eccesso_atto_su_ape > margine_fisiologico:
        gravita = "alta" if eccesso_atto_su_ape > margine_alta_gravita else "media"
        return [
            Discrepancy(
                campo="superficie_mq",
                documento_a="atto_compravendita",
                valore_a=str(val_atto),
                documento_b="ape",
                valore_b=str(val_ape),
                gravita=gravita,
                dettaglio=(
                    f"La superficie commerciale in atto supera quella utile in APE del "
                    f"{eccesso_atto_su_ape:.0%}: un certo margine è fisiologico (balconi, "
                    "cantine, box pesati a percentuale ridotta), ma uno scarto di questa "
                    "entità va verificato su planimetria per escludere pertinenze "
                    "conteggiate in modo scorretto o un errore di trascrizione."
                ),
            )
        ]
    return []


def _riferimenti_coincidono(a: RiferimentoCatastale, b: RiferimentoCatastale) -> bool:
    campi = ["foglio", "particella", "subalterno"]
    confrontabili = [(getattr(a, c), getattr(b, c)) for c in campi]
    # coincidono se tutti i campi presenti in entrambi combaciano (ignoriamo i None)
    presenti = [(x, y) for x, y in confrontabili if x is not None and y is not None]
    if not presenti:
        return True  # non abbastanza dati per dire che NON coincidono
    return all(x == y for x, y in presenti)


def _normalizza_categoria(categoria: str) -> str:
    return categoria.strip().upper().replace(" ", "")


def _gruppo_categoria(categoria: str) -> Optional[str]:
    cat = _normalizza_categoria(categoria)
    return cat.split("/")[0] if "/" in cat else None


# Le categorie del gruppo F ("F/3" fabbricato in corso di costruzione, "F/4"
# unità in corso di definizione, ecc.) sono classificazioni "fittizie"/
# transitorie, non una categoria definitiva: a fine lavori vanno sostituite
# con una categoria ordinaria (es. A/2) tramite una variazione catastale
# "di ultimazione", ma NON esiste un termine automatico nazionale dopo il
# quale il catasto le trasforma da solo — restano F finché il proprietario
# non presenta la variazione, anche per anni. Per questo, se un documento
# riporta ancora una categoria F e un altro (più recente) ne riporta già una
# definitiva per lo stesso identificativo catastale, NON è di per sé un
# errore o un "immobile diverso": è il segnale tipico di un aggiornamento
# catastale non ancora presentato — un caso diverso, e meno grave, di due
# categorie definitive che non coincidono tra loro (che invece non ha una
# spiegazione fisiologica di questo tipo).
# Fonti: [ACCA — categorie catastali F/3 e F/4](https://biblus.acca.it/categorie-catastali-f3-f4-accatastamento-di-fabbricati-in-costruzione/);
# [edilizia.com — categoria F/3, obbligo di variazione e conformità catastale in sede di atto](https://www.edilizia.com/catasto/categoria-catastale-f3-fabbricati-corso-costruzione-tassazione/)
# (quest'ultima fonte segnala anche che per le unità ancora F/3 non è possibile
# la dichiarazione di conformità catastale delle planimetrie — Circolare
# Agenzia del Territorio 2/T del 2010 — un motivo in più per verificare la
# variazione prima del rogito).
_GRUPPO_CATASTALE_TRANSITORIO = "F"


def check_riferimenti_catastali(
    docs: dict[str, Optional[BaseModel]],
) -> list[Discrepancy]:
    """Verifica che i riferimenti catastali coincidano tra tutti i documenti
    del fascicolo che li riportano, su due livelli distinti:

    1. foglio/particella/subalterno: se non coincidono, i due documenti
       molto probabilmente non si riferiscono alla stessa unità immobiliare
       (errore di trascrizione o, più raramente, immobile diverso) — gravità
       "alta";
    2. categoria catastale: anche quando foglio/particella/subalterno
       coincidono (quindi è la STESSA unità), la categoria dichiarata può
       differire tra due documenti. Distinguiamo due casi, perché non hanno
       lo stesso significato né la stessa gravità:
       - una categoria è del gruppo "F" (transitoria/fittizia, vedi
         _GRUPPO_CATASTALE_TRANSITORIO sopra) e l'altra è una categoria
         definitiva diversa: fisiologico se l'immobile era "in costruzione"
         al momento del documento più vecchio ed è stato completato dopo —
         segnala solo che va verificata la variazione catastale di
         ultimazione, gravità "media";
       - entrambe le categorie sono definitive (nessuna delle due è "F") ma
         diverse tra loro (es. A/2 in un documento, A/3 nell'altro): non ha
         una spiegazione fisiologica di questo tipo, quindi gravità "alta".
    """
    refs: list[tuple[str, RiferimentoCatastale]] = []
    for nome, doc in docs.items():
        if doc is None:
            continue
        doc_refs = getattr(doc, "riferimenti_catastali", None)
        singolo = getattr(doc, "riferimento", None)
        if doc_refs:
            refs.extend((nome, r) for r in doc_refs)
        elif singolo:
            refs.append((nome, singolo))

    discrepanze = []
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            nome_a, ref_a = refs[i]
            nome_b, ref_b = refs[j]
            if not _riferimenti_coincidono(ref_a, ref_b):
                discrepanze.append(
                    Discrepancy(
                        campo="riferimento_catastale",
                        documento_a=nome_a,
                        valore_a=f"F{ref_a.foglio}/P{ref_a.particella}/S{ref_a.subalterno}",
                        documento_b=nome_b,
                        valore_b=f"F{ref_b.foglio}/P{ref_b.particella}/S{ref_b.subalterno}",
                        gravita="alta",
                        dettaglio=(
                            "Riferimenti catastali non coincidenti tra documenti dello "
                            "stesso fascicolo: possibile errore di trascrizione o "
                            "immobile diverso."
                        ),
                    )
                )
                continue

            # Stessa unità (F/P/S coincidono, o non ci sono abbastanza dati per
            # escluderlo): se entrambi i documenti riportano anche la categoria
            # catastale, confrontiamo pure quella.
            if not ref_a.categoria or not ref_b.categoria:
                continue
            if _normalizza_categoria(ref_a.categoria) == _normalizza_categoria(ref_b.categoria):
                continue

            gruppo_a = _gruppo_categoria(ref_a.categoria)
            gruppo_b = _gruppo_categoria(ref_b.categoria)
            coinvolge_transitoria = _GRUPPO_CATASTALE_TRANSITORIO in (gruppo_a, gruppo_b)
            if coinvolge_transitoria:
                gravita = "media"
                dettaglio = (
                    "Stesso identificativo catastale (foglio/particella/subalterno), ma "
                    f"categoria dichiarata diversa tra {nome_a} ('{ref_a.categoria}') e "
                    f"{nome_b} ('{ref_b.categoria}'): una delle due è una categoria del "
                    "gruppo F (fittizia/transitoria, es. F/3 'in corso di costruzione'), "
                    "l'altra è una categoria definitiva. Può essere fisiologico se "
                    "l'immobile era ancora in costruzione al momento del documento più "
                    "vecchio ed è stato completato in seguito, ma NON esiste un termine "
                    "automatico dopo il quale l'F/3 si trasforma da solo: verificare che "
                    "sia stata presentata la variazione catastale di ultimazione lavori "
                    "prima del rogito, perché finché l'unità resta F non è possibile la "
                    "dichiarazione di conformità catastale delle planimetrie richiesta in atto."
                )
            else:
                gravita = "alta"
                dettaglio = (
                    "Stesso identificativo catastale (foglio/particella/subalterno), ma "
                    f"categoria dichiarata diversa tra {nome_a} ('{ref_a.categoria}') e "
                    f"{nome_b} ('{ref_b.categoria}'): entrambe le categorie sono "
                    "definitive, quindi la differenza non ha una spiegazione fisiologica "
                    "di 'immobile ancora in costruzione'. Può indicare un cambio di "
                    "destinazione d'uso non aggiornato in uno dei due documenti, un "
                    "errore di trascrizione, oppure che i due documenti non descrivono "
                    "davvero la stessa situazione di fatto: verificare quale dei due è "
                    "aggiornato ed eventualmente se serve una variazione catastale."
                )
            discrepanze.append(
                Discrepancy(
                    campo="categoria_catastale",
                    documento_a=nome_a,
                    valore_a=ref_a.categoria,
                    documento_b=nome_b,
                    valore_b=ref_b.categoria,
                    gravita=gravita,
                    dettaglio=dettaglio,
                )
            )
    return discrepanze


def run_all_checks(
    atto: Optional[AttoCompravendita] = None,
    visura: Optional[VisuraCatastale] = None,
    ape: Optional[APE] = None,
    contratto: Optional[ContrattoLocazione] = None,
) -> list[Discrepancy]:
    discrepanze = []
    discrepanze += check_superficie(atto, ape)
    discrepanze += check_riferimenti_catastali(
        {
            "atto_compravendita": atto,
            "visura_catastale": visura,
            "ape": ape,
            "contratto_locazione": contratto,
        }
    )
    return discrepanze


# ---------------------------------------------------------------------------
# Missing-info detection: domande proattive al proprietario
# ---------------------------------------------------------------------------

# Per i campi più importanti usiamo una domanda "umana" curata; per gli altri
# campi mancanti generiamo una domanda generica a partire dal nome del campo.
FIELD_QUESTIONS: dict[str, str] = {
    "prezzo_eur": "Qual è il prezzo di compravendita concordato?",
    "data_atto": "In che data è stato firmato o è previsto l'atto?",
    "notaio": "Chi è il notaio incaricato dell'atto?",
    "riferimenti_catastali": "Può fornire i riferimenti catastali completi (foglio, particella, subalterno)?",
    "superficie_dichiarata_mq": "Qual è la superficie commerciale/catastale dell'immobile?",
    "presenza_mutuo_ipoteca": "Sull'immobile grava un mutuo o un'ipoteca?",
    "classe_energetica": "È disponibile l'attestato di prestazione energetica (APE) con la classe energetica?",
    "canone_mensile_eur": "Qual è il canone di locazione mensile richiesto?",
    "tipo_contratto": "Che tipo di contratto di locazione si intende utilizzare (4+4, concordato, transitorio)?",
    "diritti_e_quote": "L'immobile è di piena proprietà o gravato da usufrutto/altri diritti?",
}


@dataclass
class MissingInfo(Identifiable):
    campo: str
    domanda: str
    priorita: str
    status: str = "not_extracted"


@dataclass
class MissingInfoReport(Identifiable):
    """Domande da porre al proprietario per un singolo documento, divise per
    priorità in base al tiering dei campi definito in schemas.py
    (CAMPI_ESSENZIALI per modello, via campi_essenziali()/campi_accessori()).

    La divisione serve a non sommergere il proprietario con una lista piatta
    di richieste: le domande essenziali sono quelle senza le quali il
    documento non è utilizzabile ai fini della due diligence (dati richiesti
    per legge/prassi o che alimentano un controllo automatico) e vanno poste
    per prime / in modo più insistente; le accessorie arricchiscono il
    fascicolo ma la loro assenza non blocca l'analisi.
    """

    documento: str
    domande_essenziali: list[str]
    domande_accessorie: list[str]
    items: list[MissingInfo] = field(default_factory=list)

    @property
    def completo(self) -> bool:
        """True se non manca nessun campo essenziale (possono comunque mancare
        campi accessori)."""
        return not self.domande_essenziali

    def tutte_le_domande(self) -> list[str]:
        return self.domande_essenziali + self.domande_accessorie


def _domanda_per_campo(field_name: str) -> str:
    return FIELD_QUESTIONS.get(
        field_name, f"Può fornire informazioni sul campo '{field_name}'?"
    )


def generate_missing_info_questions(doc: BaseModel, *, property_id: str | None = None, document_id: str | None = None) -> MissingInfoReport:
    """Scorre i campi del modello estratto e propone una domanda per ognuno
    vuoto, dividendo il risultato in "essenziali" e "accessori" in base al
    tiering dichiarato dal modello (schemas.campi_essenziali/campi_accessori).

    Nota: questa è logica deterministica sullo schema, non richiede una chiamata
    LLM aggiuntiva. Se in futuro si vuole una formulazione più naturale/contestuale
    (es. che citi cosa è già noto), si può passare l'elenco di campi mancanti a
    un prompt che usa system_prompts.BASE_SYSTEM_PROMPT per generare le domande
    in linguaggio naturale invece di usare il template fisso qui sotto.
    """
    model_cls = type(doc)
    essenziali = campi_essenziali(model_cls)
    accessori = campi_accessori(model_cls)

    items = []
    domande_essenziali: list[str] = []
    domande_accessorie: list[str] = []
    for field_name, value in doc:
        comparable = getattr(value, "valore", value)
        is_empty = comparable is None or comparable == [] or comparable == ""
        if not is_empty or field_name == "note_incertezza":
            continue
        if field_name in essenziali:
            domande_essenziali.append(_domanda_per_campo(field_name))
        elif field_name in accessori:
            domande_accessorie.append(_domanda_per_campo(field_name))
        if field_name in essenziali or field_name in accessori:
            item = MissingInfo(campo=field_name, domanda=_domanda_per_campo(field_name),
                               priorita="essential" if field_name in essenziali else "optional",
                               property_id=property_id, document_ids=[document_id] if document_id else [],
                               lineage_status="document_linked" if property_id and document_id else "unbound")
            if property_id and document_id:
                item.object_id = stable_id("missing-field", property_id, document_id, field_name)
            items.append(item)
        # campi non tierati (metadati di pipeline, es. tipo_documento) sono
        # ignorati: non generano mai una domanda.

    tipo_doc = getattr(doc, "tipo_documento", None)
    nome_documento = getattr(tipo_doc, "value", None) or model_cls.__name__
    return MissingInfoReport(
        documento=nome_documento, items=items, property_id=property_id,
        document_ids=[document_id] if document_id else [],
        lineage_status="document_linked" if property_id and document_id else "unbound",
        domande_essenziali=domande_essenziali,
        domande_accessorie=domande_accessorie,
    )


