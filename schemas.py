"""
Schemi (leva 2) per l'estrazione strutturata dai documenti immobiliari.

Ogni tipo di documento ha il proprio modello Pydantic. Il modello serve a due scopi:
1. È lo "schema JSON" che passiamo all'API di Claude (tool_use / structured output)
   per forzare l'estrazione in un formato prevedibile, invece di ricevere testo libero.
2. È la struttura su cui il consistency engine confronta i campi tra documenti diversi
   (es. superficie dichiarata nell'atto vs. in planimetria vs. in APE).

Convenzioni comuni:
- Ogni campo "di valore" è accompagnato, dove utile, da un campo _fonte che riporta
  la frase o la posizione nel documento da cui è stato estratto (per audit trail e
  per permettere al frontend di mostrare la citazione).
- Se un'informazione non è presente nel documento, il campo va lasciato a None:
  MAI inventare un valore plausibile. Questo è rinforzato anche dal system prompt.
- confidence (0-1) esprime quanto il modello è certo dell'estrazione di quel campo;
  serve al freelancer/Milestone 2 (confidence score) e al missing-info detection.
"""

from __future__ import annotations

from enum import Enum
from typing import ClassVar, Optional, Literal

from pydantic import BaseModel, Field

# Campi presenti in (quasi) ogni modello che non sono mai "dati del documento"
# in senso proprio (sono metadati della pipeline) e quindi non vengono mai
# considerati né essenziali né accessori nel missing-info detection.
_CAMPI_META = frozenset({"tipo_documento", "note_incertezza"})


class TipoDocumento(str, Enum):
    ATTO_COMPRAVENDITA = "atto_compravendita"
    VISURA_CATASTALE = "visura_catastale"
    APE = "ape"
    PLANIMETRIA = "planimetria"
    CONTRATTO_LOCAZIONE = "contratto_locazione"
    VISURA_IPOTECARIA = "visura_ipotecaria"
    CERTIFICATO_DESTINAZIONE_URBANISTICA = "certificato_destinazione_urbanistica"
    TITOLO_EDILIZIO = "titolo_edilizio"
    CERTIFICATO_AGIBILITA = "certificato_agibilita"
    REGOLAMENTO_CONDOMINIO = "regolamento_condominio"
    VERBALE_ASSEMBLEA_CONDOMINIO = "verbale_assemblea_condominio"
    DICHIARAZIONE_CONFORMITA_IMPIANTI = "dichiarazione_conformita_impianti"
    ATTO_DI_PROVENIENZA = "atto_di_provenienza"
    PRELIMINARE_COMPRAVENDITA = "preliminare_compravendita"
    RELAZIONE_TECNICA_INTEGRATA = "relazione_tecnica_integrata"
    PERIZIA_DI_STIMA = "perizia_di_stima"
    LICENZA_COMMERCIALE = "scia_licenza_commerciale"
    CERTIFICATO_PREVENZIONE_INCENDI = "certificato_prevenzione_incendi"
    VISURA_CAMERALE = "visura_camerale"
    ALTRO = "altro"


class CampoEstratto(BaseModel):
    """Wrapper generico per un valore estratto + la sua fonte/confidenza.

    Non tutti i campi dei modelli sotto usano questo wrapper (per non appesantire
    troppo lo schema passato al modello): lo usiamo sui campi più critici per la
    due diligence (importi, superfici, riferimenti catastali).
    """

    valore: Optional[str] = None
    fonte: Optional[str] = Field(
        default=None,
        description="Frase o riferimento (es. 'pag. 2, art. 3') da cui è stato estratto il valore",
    )
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    valore_in_lettere: Optional[str] = Field(
        default=None,
        description=(
            "SOLO per importi in denaro: la stessa somma scritta per disteso in lettere, se il "
            "documento la riporta. Non è un dettaglio opzionale da cogliere solo se avanza tempo: "
            "la legge notarile impone di scrivere le somme di denaro anche per disteso, almeno alla "
            "prima menzione, proprio per prevenire alterazioni (art. 51, n. 5, L. 89/1913) — quindi "
            "in un atto di compravendita questo dato è quasi SEMPRE presente accanto alla cifra "
            "(tipica formula 'Euro 285.000,00 (diconsi Euro duecentottantacinquemila/00)'), ma viene "
            "facilmente ignorato in estrazione perché sembra ridondante rispetto alla cifra. Riporta "
            "SOLO la parte in lettere (es. 'duecentottantacinquemila'), non l'intera frase con "
            "'Euro' o 'diconsi': permette un controllo di coerenza deterministico e gratuito tra le "
            "due forme (validators.verifica_importo_in_lettere), indipendente da qualunque verifica "
            "LLM — se le due forme non coincidono è un segnale che nella redazione dell'atto (o "
            "nell'OCR/estrazione) qualcosa non torna."
        ),
    )


class RiferimentoCatastale(BaseModel):
    comune: Optional[str] = None
    sezione: Optional[str] = None
    foglio: Optional[str] = None
    particella: Optional[str] = None
    subalterno: Optional[str] = None
    categoria: Optional[str] = None  # es. A/2, A/3, C/6...
    classe: Optional[str] = None
    consistenza: Optional[str] = None  # es. "5,5 vani" oppure mq per categorie diverse da A
    rendita_catastale_eur: Optional[float] = None
    indirizzo: Optional[str] = None
    ruolo_unita: Optional[Literal["principale", "pertinenza"]] = Field(default=None,
        description="Solo se esplicitamente indicato per questa unità nel documento. Non dedurre il ruolo dalla categoria catastale: C/2 non significa automaticamente pertinenza.")


class TitolaritaEstratta(BaseModel):
    """Una riga per soggetto, diritto e unità: non aggregare diritti diversi."""
    soggetto: Optional[str] = None
    diritto: Optional[Literal["proprieta", "nuda_proprieta", "usufrutto", "uso", "abitazione", "superficie", "altro"]] = None
    quota: Optional[str] = Field(default=None, description="Frazione o percentuale riportata, es. 1/2 o 50%. Non dedurre quote mancanti.")
    riferimento: Optional[RiferimentoCatastale] = None
    fonte: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)


class FormalitaEstratta(BaseModel):
    identificativo: Optional[str] = Field(default=None, description="Identità completa della nota: ufficio, anno, registro e numero, solo quanto esplicito. Non usare il solo numero se ambiguo.")
    tipo: Optional[str] = None
    stato: Optional[Literal["attiva", "cancellata", "cancellazione_parziale", "cancellazione_richiesta", "non_determinabile"]] = Field(default=None,
        description="Solo stato esplicitamente documentato; mutuo estinto o impegno a cancellare non equivalgono a cancellazione.")
    data_riferimento: Optional[str] = None
    riferimento: Optional[RiferimentoCatastale] = None
    fonte: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)


class CondizioneContrattuale(BaseModel):
    identificativo: Optional[str] = None
    descrizione: Optional[str] = None
    stato: Optional[Literal["pendente", "avverata", "non_avverata", "rinunciata", "non_determinabile"]] = Field(default=None,
        description="Solo esito attestato nel documento, mai dedotto dal trascorrere del tempo o dalla formula della condizione.")
    data_scadenza: Optional[str] = None
    fonte: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)


class CollegamentoOperazione(BaseModel):
    riferimento: Optional[str] = Field(default=None,
        description="Estremi completi dell’operazione/preliminare richiamato esplicitamente: includere ufficio/registro/numero quando riportati. Non inventare un collegamento da stesso immobile, parti o prezzo.")
    data: Optional[str] = Field(default=None, description="Data dell’operazione/preliminare identificato dal riferimento, non la data del documento che lo richiama.")
    stato_documento: Optional[Literal["bozza", "sottoscritto", "non_determinabile"]] = Field(default=None,
        description="Stato di QUESTO documento, solo se ricavabile dal testo o dalle firme; il titolo 'atto' non basta.")
    fonte: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)


class AttoCompravendita(BaseModel):
    """Elementi essenziali secondo gli essentialia negotii del contratto di
    compravendita (accordo delle parti, oggetto, prezzo, forma — art. 1470 e ss.
    c.c.) più i campi che alimentano i controlli automatici del sistema
    (superficie per consistency.check_superficie, data per red_flags.check_spese_straordinarie_ante_rogito).
    Fonte generale sugli essentialia negotii: https://www.lexplain.it/contratto-di-compravendita/"""

    CAMPI_ESSENZIALI: ClassVar[frozenset[str]] = frozenset(
        {"parte_venditrice", "parte_acquirente", "riferimenti_catastali", "prezzo_eur", "superficie_dichiarata_mq", "data_atto"}
    )

    tipo_documento: TipoDocumento = TipoDocumento.ATTO_COMPRAVENDITA
    collegamento_operazione: Optional[CollegamentoOperazione] = None
    condizioni_dettaglio: list[CondizioneContrattuale] = Field(default_factory=list,
        description="Esiti di condizioni del preliminare, solo se espressamente richiamati con identificativo e citazione. Non dedurre l’avveramento dalla presenza dell’atto definitivo.")
    data_atto: Optional[str] = Field(default=None, description="Formato ISO YYYY-MM-DD se ricavabile")
    notaio: Optional[str] = None
    parte_venditrice: list[str] = Field(default_factory=list)
    parte_acquirente: list[str] = Field(default_factory=list)
    prezzo_eur: Optional[CampoEstratto] = None
    modalita_pagamento: Optional[str] = None
    riferimenti_catastali: list[RiferimentoCatastale] = Field(default_factory=list)
    superficie_dichiarata_mq: Optional[CampoEstratto] = None
    presenza_mutuo_ipoteca: Optional[bool] = None
    ape_menzionato_in_atto: Optional[bool] = Field(
        default=None,
        description=(
            "True se il testo dell'atto contiene la clausola relativa all'attestato di prestazione "
            "energetica (APE): tipicamente gli estremi (classe energetica, numero identificativo) più "
            "la dichiarazione delle parti di averne preso visione e/o riceverne copia allegata — "
            "obbligatoria per legge in ogni atto di trasferimento immobiliare a titolo oneroso. False "
            "se, leggendo il testo COMPLETO dell'atto, questa clausola non compare affatto (a "
            "differenza di altri campi booleani di questo schema, qui False è una conclusione utile e "
            "frequente, non da riservare solo a una negazione esplicita: un atto completo che non "
            "contiene la clausola è un dato di fatto rilevabile dalla lettura, non un'informazione "
            "mancante). None solo se il testo fornito è un frammento/estratto da cui non si può "
            "concludere in un senso o nell'altro."
        ),
    )
    agevolazioni_prima_casa_richieste: Optional[bool] = Field(
        default=None,
        description=(
            "True SOLO se l'atto dichiara esplicitamente che l'acquirente richiede le agevolazioni "
            "'prima casa' (aliquota ridotta di imposta di registro/IVA): tipicamente due dichiarazioni "
            "dell'acquirente (non possedere altra casa idonea nello stesso Comune; non essere "
            "titolare altrove di un'altra prima casa già agevolata) più l'impegno a trasferire la "
            "residenza nel Comune entro 18 mesi. False se l'atto dichiara esplicitamente il contrario "
            "(es. acquisto a aliquota ordinaria); None se il documento non lo specifica."
        ),
    )
    regime_patrimoniale_dichiarato: Optional[str] = Field(
        default=None,
        description=(
            "Regime patrimoniale del/i venditore/i persona fisica, SOLO se l'atto lo dichiara"
            "esplicitamente (formula tipica: 'coniugato/a in regime di comunione legale dei beni "
            "con...' oppure '...di separazione dei beni'; oppure una dichiarazione ex art. 179 c.c. "
            "che il bene è personale). Riporta la dicitura così come compare, non dedurla: se il "
            "documento non menziona affatto lo stato civile/regime, lascia None (il regime legale "
            "di comunione è il default in Italia salvo scelta contraria, ma un'estrazione non deve "
            "MAI presumerlo in assenza di una dichiarazione testuale — vedi validators/red_flags per "
            "cosa succede quando questo campo è valorizzato con 'comunione' e un solo coniuge vende)."
        ),
    )
    clausole_rilevanti: list[str] = Field(
        default_factory=list,
        description="Clausole degne di attenzione per la due diligence: condizioni sospensive, penali, garanzie, servitù",
    )
    note_incertezza: list[str] = Field(
        default_factory=list,
        description="Elenco di punti in cui il modello non è sicuro dell'estrazione o il testo è ambiguo",
    )


class VisuraCatastale(BaseModel):
    """I dati identificativi catastali (sezione/foglio/particella/subalterno) e
    l'intestazione (chi è il titolare e di quale diritto) sono i due elementi
    che una visura serve sempre a fornire — sono ciò che permette di collegare
    (consistency engine) e verificare la titolarità di questo immobile rispetto
    agli altri documenti del fascicolo. Fonte: condominioweb.com su dati
    obbligatori di una visura catastale."""

    CAMPI_ESSENZIALI: ClassVar[frozenset[str]] = frozenset(
        {"riferimento", "intestatari", "diritti_e_quote"}
    )

    tipo_documento: TipoDocumento = TipoDocumento.VISURA_CATASTALE
    titolarita: list[TitolaritaEstratta] = Field(default_factory=list)
    elenco_titolari_completo: Optional[bool] = Field(default=None,
        description="True solo se la fonte attesta l’elenco completo per i diritti e le unità riportati; non presumere completezza di un estratto.")
    intestatari: list[str] = Field(default_factory=list)
    codici_fiscali_intestatari: list[str] = Field(
        default_factory=list,
        description="Codici fiscali degli intestatari, nello stesso ordine di 'intestatari', copiati carattere per carattere",
    )
    riferimento: Optional[RiferimentoCatastale] = None
    superficie_catastale_mq: Optional[float] = Field(
        default=None, description="Superficie catastale in m² se riportata nella visura"
    )
    data_visura: Optional[str] = None
    diritti_e_quote: Optional[str] = Field(
        default=None, description="es. 'proprietà per 1/1', 'usufrutto per 1/2'"
    )
    note_incertezza: list[str] = Field(default_factory=list)


class APE(BaseModel):
    """Il contenuto obbligatorio dell'APE è fissato dall'art. 6 comma 12 lett. b)
    del d.lgs. 192/2005: dati identificativi dell'edificio/unità, classe
    energetica, indice di prestazione, dati del certificatore e validità
    (10 anni, salvo interventi). La superficie utile alimenta inoltre
    consistency.check_superficie. Fonte: lavoripubblici.it sul contenuto
    obbligatorio dell'APE."""

    CAMPI_ESSENZIALI: ClassVar[frozenset[str]] = frozenset(
        {"classe_energetica", "riferimenti_catastali", "superficie_utile_mq", "data_scadenza"}
    )

    tipo_documento: TipoDocumento = TipoDocumento.APE
    classe_energetica: Optional[str] = None
    epgl_kwh_mq_anno: Optional[float] = Field(
        default=None, description="Indice di prestazione energetica globale"
    )
    superficie_utile_mq: Optional[CampoEstratto] = None
    data_emissione: Optional[str] = None
    data_scadenza: Optional[str] = None
    soggetto_certificatore: Optional[str] = None
    riferimenti_catastali: list[RiferimentoCatastale] = Field(default_factory=list)
    note_incertezza: list[str] = Field(default_factory=list)


class ContrattoLocazione(BaseModel):
    """La L. 431/98 individua gli elementi che qualificano il tipo di contratto
    (locatore/conduttore, canone, durata, tipologia 4+4/concordato/transitorio)
    e che determinano il regime applicabile (es. durata minima, disdetta).
    L'identificazione catastale dell'immobile locato è richiesta ai fini della
    registrazione. Fonte: ricerca su contratto di locazione e L. 431/98.

    Il campo `uso` (abitativo/commerciale/altro) alimenta un controllo con
    conseguenze potenzialmente molto gravi per l'agente che gestisce una
    vendita: se l'uso è commerciale/non abitativo, il conduttore ha diritto
    di prelazione sulla vendita dell'immobile ex art. 38-39 L. 392/1978 (vedi
    red_flags.check_prelazione_conduttore_commerciale) — se non rispettato,
    l'atto può essere riscattato dal conduttore entro 6 mesi.

    Il campo `registrato` va valorizzato SOLO se il documento (o un allegato,
    es. ricevuta di registrazione con CIR) lo dichiara esplicitamente: il
    contratto in sé di norma non attesta la propria registrazione, che è un
    fatto successivo alla firma. Non dedurre False dalla semplice assenza di
    menzione: lascia None se il testo non lo dice."""

    CAMPI_ESSENZIALI: ClassVar[frozenset[str]] = frozenset(
        {"locatore", "conduttore", "canone_mensile_eur", "durata", "riferimenti_catastali", "tipo_contratto", "uso"}
    )

    tipo_documento: TipoDocumento = TipoDocumento.CONTRATTO_LOCAZIONE
    locatore: list[str] = Field(default_factory=list)
    conduttore: list[str] = Field(default_factory=list)
    canone_mensile_eur: Optional[CampoEstratto] = None
    durata: Optional[str] = None
    data_inizio: Optional[str] = None
    data_fine: Optional[str] = Field(default=None, description="Termine esplicito. Non calcolarlo dalla durata né dedurre cessazione effettiva o mancato rinnovo.")
    canone_annuo_eur: Optional[CampoEstratto] = None
    tipo_contratto: Optional[str] = Field(
        default=None, description="es. 4+4, transitorio, concordato"
    )
    uso: Optional[str] = Field(
        default=None,
        description="abitativo, commerciale, ufficio, artigianale, altro non abitativo",
    )
    registrato: Optional[bool] = Field(
        default=None,
        description="True/False SOLO se dichiarato esplicitamente nel documento o in un allegato; altrimenti None",
    )
    riferimenti_catastali: list[RiferimentoCatastale] = Field(default_factory=list)
    note_incertezza: list[str] = Field(default_factory=list)


class VisuraIpotecaria(BaseModel):
    """Il compito di questo documento nella due diligence è uno solo: dire se
    esiste una formalità pregiudizievole ancora attiva sull'immobile (e di che
    tipo — ipoteca volontaria vs. pignoramento/sequestro cambia radicalmente la
    gravità, vedi red_flags.check_formalita_pregiudizievoli) e per quale
    importo. Questi quattro campi sono ciò che rende il documento utile;
    il resto è corredo."""

    CAMPI_ESSENZIALI: ClassVar[frozenset[str]] = frozenset(
        {"tipo_formalita", "formalita_ancora_attiva", "riferimenti_catastali", "importo_iscrizione_eur"}
    )

    tipo_documento: TipoDocumento = TipoDocumento.VISURA_IPOTECARIA
    formalita: list[FormalitaEstratta] = Field(default_factory=list)
    soggetti: list[str] = Field(default_factory=list)
    tipo_formalita: Optional[str] = Field(
        default=None, description="es. ipoteca volontaria, pignoramento, sequestro"
    )
    importo_iscrizione_eur: Optional[CampoEstratto] = None
    data_iscrizione: Optional[str] = None
    ente_creditore: Optional[str] = None
    riferimenti_catastali: list[RiferimentoCatastale] = Field(default_factory=list)
    formalita_ancora_attiva: Optional[bool] = Field(
        default=None,
        description="Stato esplicito della formalità nella fonte. None se non determinabile; non dedurre attività o cancellazione dall’assenza di una pagina o annotazione.",
    )
    note_incertezza: list[str] = Field(default_factory=list)


class Planimetria(BaseModel):
    """La planimetria serve alla due diligence soprattutto per il confronto
    incrociato della superficie/consistenza con atto e APE (consistency engine)
    e per collegare il disegno depositato all'unità catastale corretta; il
    resto (scala, numero vani, data deposito) è utile ma accessorio."""

    CAMPI_ESSENZIALI: ClassVar[frozenset[str]] = frozenset(
        {"riferimenti_catastali", "superficie_calcolata_mq"}
    )

    tipo_documento: TipoDocumento = TipoDocumento.PLANIMETRIA
    scala: Optional[str] = None
    superficie_calcolata_mq: Optional[CampoEstratto] = None
    numero_vani: Optional[int] = None
    riferimenti_catastali: list[RiferimentoCatastale] = Field(default_factory=list)
    data_deposito: Optional[str] = None
    note_incertezza: list[str] = Field(default_factory=list)


class CertificatoDestinazioneUrbanistica(BaseModel):
    """CDU: rilasciato dal Comune, indica la destinazione urbanistica e gli
    eventuali vincoli (paesaggistici, idrogeologici, sismici, archeologici) che
    gravano sull'area. Rilevante soprattutto per terreni e per capire se
    l'immobile è in un'area con vincoli che limitano interventi futuri."""

    CAMPI_ESSENZIALI: ClassVar[frozenset[str]] = frozenset({"vincoli", "riferimenti_catastali"})

    tipo_documento: TipoDocumento = TipoDocumento.CERTIFICATO_DESTINAZIONE_URBANISTICA
    comune: Optional[str] = None
    data_rilascio: Optional[str] = None
    destinazione_urbanistica: Optional[str] = Field(
        default=None, description="es. 'zona B - residenziale di completamento'"
    )
    vincoli: list[str] = Field(
        default_factory=list,
        description="es. vincolo paesaggistico, idrogeologico, sismico, archeologico, storico-artistico",
    )
    riferimenti_catastali: list[RiferimentoCatastale] = Field(default_factory=list)
    note_incertezza: list[str] = Field(default_factory=list)


class TitoloEdilizio(BaseModel):
    """Permesso di costruire, CILA, SCIA, condono edilizio: il titolo che
    autorizza (o ha sanato) una costruzione o una modifica. La 'catena' dei
    titoli edilizi di un immobile, confrontata con lo stato di fatto rilevabile
    da planimetria/foto, è alla base della verifica di conformità urbanistica
    (concetto distinto dalla conformità catastale)."""

    CAMPI_ESSENZIALI: ClassVar[frozenset[str]] = frozenset(
        {"tipo_titolo", "stato", "riferimenti_catastali"}
    )

    tipo_documento: TipoDocumento = TipoDocumento.TITOLO_EDILIZIO
    tipo_titolo: Optional[str] = Field(
        default=None,
        description="permesso di costruire, CILA, SCIA, condono edilizio, licenza edilizia (immobili ante 1967/1977)",
    )
    numero_pratica: Optional[str] = None
    data_rilascio_o_presentazione: Optional[str] = None
    oggetto_lavori: Optional[str] = None
    destinazione_uso: Optional[CampoEstratto] = Field(default=None,
        description="Uso autorizzato esplicitamente dal titolo, con citazione. Non confondere uso esistente, proposto o oggetto di istanza non ancora conclusa; se ambiguo lascia None e spiega nelle note.")
    stato: Optional[str] = Field(
        default=None, description="es. rilasciato, in istruttoria, decaduto, in sanatoria"
    )
    riferimenti_catastali: list[RiferimentoCatastale] = Field(default_factory=list)
    note_incertezza: list[str] = Field(default_factory=list)


class CertificatoAgibilita(BaseModel):
    """Attesta che l'immobile rispetta i requisiti di sicurezza, igiene, salubrità
    e risparmio energetico. La sua assenza non rende nullo l'atto ma può essere
    un vizio della cosa venduta con conseguenze risarcitorie."""

    CAMPI_ESSENZIALI: ClassVar[frozenset[str]] = frozenset({"riferimenti_catastali"})

    tipo_documento: TipoDocumento = TipoDocumento.CERTIFICATO_AGIBILITA
    protocollo: Optional[str] = None
    data_rilascio: Optional[str] = None
    comune: Optional[str] = None
    riferimenti_catastali: list[RiferimentoCatastale] = Field(default_factory=list)
    note_incertezza: list[str] = Field(default_factory=list)


class RegolamentoCondominio(BaseModel):
    """Il regolamento 'contrattuale' (approvato all'unanimità o richiamato negli
    atti di acquisto) può contenere limitazioni all'uso dell'unità (es. divieto
    di destinazione commerciale, divieto di affitti brevi) opponibili a tutti i
    proprietari; quello 'assembleare' ha efficacia più limitata."""

    CAMPI_ESSENZIALI: ClassVar[frozenset[str]] = frozenset(
        {"tipo_regolamento", "limitazioni_uso"}
    )

    tipo_documento: TipoDocumento = TipoDocumento.REGOLAMENTO_CONDOMINIO
    tipo_regolamento: Optional[str] = Field(
        default=None, description="'contrattuale' o 'assembleare/interno'"
    )
    limitazioni_uso: list[str] = Field(
        default_factory=list,
        description="es. divieto attività commerciali, divieto affitti brevi, divieto animali",
    )
    data: Optional[str] = None
    note_incertezza: list[str] = Field(default_factory=list)


class DeliberaCondominio(BaseModel):
    oggetto: Optional[str] = None
    data_delibera: Optional[str] = None
    importo_totale_eur: Optional[float] = None
    quota_a_carico_unita_eur: Optional[float] = None
    lavori_gia_eseguiti: Optional[bool] = None


class VerbaleAssembleaCondominio(BaseModel):
    """I lavori straordinari DELIBERATI prima del rogito sono di norma a carico
    di chi era proprietario al momento della delibera (il venditore), anche se
    eseguiti/fatturati dopo — salvo diverso accordo tra le parti nell'atto.
    Un verbale con delibere di spesa straordinaria non ancora eseguite è quindi
    un punto da chiarire esplicitamente nell'atto."""

    CAMPI_ESSENZIALI: ClassVar[frozenset[str]] = frozenset(
        {"data_assemblea", "delibere", "morosita_menzionata"}
    )

    tipo_documento: TipoDocumento = TipoDocumento.VERBALE_ASSEMBLEA_CONDOMINIO
    data_assemblea: Optional[str] = None
    delibere: list[DeliberaCondominio] = Field(default_factory=list)
    morosita_menzionata: Optional[bool] = Field(
        default=None, description="True se il verbale menziona condomini morosi o azioni di recupero crediti"
    )
    fondo_cassa_eur: Optional[float] = None
    note_incertezza: list[str] = Field(default_factory=list)


class DichiarazioneConformitaImpianti(BaseModel):
    """Dichiarazione di conformità (ex L. 46/90, ora DM 37/2008) per impianto
    elettrico, idraulico, gas, termico. La sua assenza non blocca la vendita ma
    è un elemento di rischio/trattativa e va segnalata."""

    CAMPI_ESSENZIALI: ClassVar[frozenset[str]] = frozenset({"tipo_impianto", "conforme"})

    tipo_documento: TipoDocumento = TipoDocumento.DICHIARAZIONE_CONFORMITA_IMPIANTI
    tipo_impianto: Optional[str] = Field(
        default=None, description="elettrico, idraulico, gas, termico/climatizzazione, ascensore"
    )
    conforme: Optional[bool] = None
    data: Optional[str] = None
    tecnico_o_ditta: Optional[str] = None
    note_incertezza: list[str] = Field(default_factory=list)


class LicenzaCommerciale(BaseModel):
    """SCIA o licenza per l'esercizio di un'attività commerciale nel locale
    (distinta dalla SCIA edilizia, che riguarda lavori: vedi TitoloEdilizio).
    Conferma che l'attività effettivamente svolta è autorizzata: un'attività
    diversa da quella dichiarata, o l'assenza del titolo, espone il nuovo
    gestore a sanzioni o alla sospensione dell'attività."""

    CAMPI_ESSENZIALI: ClassVar[frozenset[str]] = frozenset({"attivita_dichiarata", "riferimenti_catastali"})

    tipo_documento: TipoDocumento = TipoDocumento.LICENZA_COMMERCIALE
    tipo_titolo: Optional[str] = Field(default=None, description="SCIA, licenza, autorizzazione")
    attivita_dichiarata: Optional[str] = Field(
        default=None, description="es. 'commercio al dettaglio di abbigliamento', 'somministrazione alimenti e bevande'"
    )
    codice_ateco: Optional[str] = None
    comune_sportello: Optional[str] = Field(default=None, description="Comune o SUAP presso cui è stata presentata")
    data_presentazione_o_rilascio: Optional[str] = None
    intestatario: Optional[str] = None
    riferimenti_catastali: list[RiferimentoCatastale] = Field(default_factory=list)
    note_incertezza: list[str] = Field(default_factory=list)


class CertificatoPrevenzioneIncendi(BaseModel):
    """CPI (o SCIA antincendio) rilasciato dai Vigili del Fuoco per le
    attività soggette al DPR 151/2011: rilevante per capannoni, magazzini e
    centri commerciali sopra certe soglie di superficie o affollamento. Ha
    validità periodica: se scaduto, l'attività non può proseguire
    legalmente finché non viene rinnovato."""

    CAMPI_ESSENZIALI: ClassVar[frozenset[str]] = frozenset({"data_scadenza", "riferimenti_catastali"})

    tipo_documento: TipoDocumento = TipoDocumento.CERTIFICATO_PREVENZIONE_INCENDI
    numero_pratica_vvf: Optional[str] = None
    categoria_rischio: Optional[str] = Field(default=None, description="A, B o C ai sensi del DPR 151/2011")
    attivita_soggetta: Optional[str] = Field(default=None, description="es. 'attività 70 - depositi con superficie superiore a...'")
    data_rilascio: Optional[str] = None
    data_scadenza: Optional[str] = None
    comune: Optional[str] = None
    riferimenti_catastali: list[RiferimentoCatastale] = Field(default_factory=list)
    note_incertezza: list[str] = Field(default_factory=list)


class VisuraCamerale(BaseModel):
    """Visura del Registro Imprese: identifica la società venditrice, la sua
    forma giuridica, lo stato dell'attività e chi ha i poteri di firma per
    impegnarla nell'atto. Una società non attiva (cessata, in liquidazione o
    sottoposta a procedura concorsuale) o un firmatario senza poteri
    sufficienti possono rendere nullo o annullabile l'atto."""

    CAMPI_ESSENZIALI: ClassVar[frozenset[str]] = frozenset({"stato_attivita", "ragione_sociale"})

    tipo_documento: TipoDocumento = TipoDocumento.VISURA_CAMERALE
    ragione_sociale: Optional[str] = None
    forma_giuridica: Optional[str] = Field(default=None, description="es. S.r.l., S.p.A., S.n.c.")
    partita_iva: Optional[str] = None
    sede_legale: Optional[str] = None
    stato_attivita: Optional[str] = Field(
        default=None, description="es. attiva, cessata, in liquidazione, fallimento, concordato preventivo"
    )
    data_iscrizione: Optional[str] = None
    data_visura: Optional[str] = Field(default=None, description="Data di generazione della visura, per capirne l'aggiornamento")
    rappresentanti_legali: list[str] = Field(
        default_factory=list, description="Nomi e poteri di firma, es. 'Mario Rossi - amministratore unico, firma singola'"
    )
    note_incertezza: list[str] = Field(default_factory=list)


class AttoDiProvenienza(BaseModel):
    """Il titolo con cui l'attuale venditore ha acquisito l'immobile (non
    l'atto di vendita corrente, ma quello precedente). Il tipo di provenienza
    cambia profondamente il profilo di rischio: una provenienza donativa
    espone l'acquirente al rischio di azione di restituzione da parte dei
    legittimari lesi (fino a 20 anni dalla trascrizione della donazione; azione
    di riduzione esperibile dai legittimari entro 10 anni dalla morte del
    donante), il che spiega la riluttanza delle banche a concedere mutui su
    questi immobili senza garanzie accessorie (fideiussione, rinuncia dei
    legittimari, risoluzione consensuale della donazione)."""

    # successione_divisa NON è tra gli essenziali: è rilevante solo quando
    # tipo_provenienza è "successione" (condizionale), quindi trattarlo come
    # sempre-necessario genererebbe un falso "manca" ogni volta che la
    # provenienza è, ad esempio, una donazione o una compravendita.
    CAMPI_ESSENZIALI: ClassVar[frozenset[str]] = frozenset({"tipo_provenienza", "data_atto"})

    tipo_documento: TipoDocumento = TipoDocumento.ATTO_DI_PROVENIENZA
    tipo_provenienza: Optional[str] = Field(
        default=None,
        description="compravendita, successione (eredità), donazione, permuta, usucapione, altro",
    )
    data_atto: Optional[str] = None
    dante_causa: list[str] = Field(
        default_factory=list, description="chi ha trasferito l'immobile all'attuale venditore"
    )
    avente_causa: list[str] = Field(
        default_factory=list, description="l'attuale venditore, così come risulta da questo atto"
    )
    successione_divisa: Optional[bool] = Field(
        default=None,
        description="se tipo_provenienza è successione: se l'eredità risulta divisa tra i coeredi (rilevante per la comunione)",
    )
    agevolazioni_prima_casa_dichiarate: Optional[bool] = Field(
        default=None,
        description=(
            "True SOLO se QUESTO atto (con cui l'attuale venditore ha a sua volta acquisito "
            "l'immobile) dichiara esplicitamente che l'acquirente di allora — cioè l'attuale "
            "venditore — aveva richiesto le agevolazioni 'prima casa'. Rilevante insieme a data_atto: "
            "se l'attuale venditore rivende entro 5 anni da QUESTO acquisto senza aver già riacquistato "
            "un'altra prima casa entro un anno dalla vendita, decade dal beneficio (recupero "
            "dell'imposta, sovrattassa del 30%, interessi) — vedi "
            "red_flags.check_decadenza_prima_casa_venditore. None se il documento non lo specifica: "
            "non dedurlo dal fatto che l'aliquota applicata sembri ridotta, solo da una dichiarazione "
            "esplicita."
        ),
    )
    coniuge_superstite_presente: Optional[bool] = Field(
        default=None,
        description=(
            "SOLO quando tipo_provenienza è 'successione': True se il testo dichiara che il defunto "
            "(dante_causa) era coniugato o in unione civile al momento del decesso, con un coniuge/"
            "unito civilmente superstite (tipica formula 'il de cuius, coniugato con...'). Rilevante "
            "perché il coniuge superstite ha per legge un diritto di abitazione sulla casa adibita a "
            "residenza familiare del defunto (art. 540, comma 2, c.c.), automatico e opponibile anche "
            "a un futuro acquirente SENZA bisogno di trascrizione — un rischio facile da non vedere "
            "perché non risulta necessariamente da nessuna visura. Vedi "
            "red_flags.check_diritto_abitazione_coniuge_superstite. None se il testo non specifica lo "
            "stato civile del defunto."
        ),
    )
    diritto_abitazione_coniuge_rinunciato: Optional[bool] = Field(
        default=None,
        description=(
            "SOLO se coniuge_superstite_presente è True: True se il testo dichiara che il coniuge "
            "superstite ha formalmente rinunciato (tipicamente con atto notarile dedicato, distinto "
            "dall'eventuale rinuncia all'eredità) al proprio diritto di abitazione su questo immobile. "
            "None se non specificato: NON dedurre la rinuncia dal solo fatto che il coniuge non compaia "
            "come parte in questo atto — la rinuncia all'eredità e la rinuncia al diritto di abitazione "
            "sono giuridicamente autonome, quindi un coniuge può aver rinunciato all'eredità e "
            "conservare comunque il diritto di abitazione."
        ),
    )
    regime_patrimoniale_dichiarato: Optional[str] = Field(
        default=None,
        description=(
            "Come per AttoCompravendita.regime_patrimoniale_dichiarato, ma riferito a QUESTO atto: "
            "il regime patrimoniale con cui l'attuale venditore (avente_causa) ha acquisito "
            "l'immobile, se dichiarato esplicitamente nel testo. Rilevante quando tipo_provenienza è "
            "'compravendita': se l'attuale venditore l'ha acquistato da solo ma in comunione legale, "
            "il coniuge può essere comproprietario automatico anche senza comparire in questo atto "
            "(art. 177 c.c.) — vedi red_flags.check_comunione_legale_coniuge_non_intervenuto."
        ),
    )
    riferimenti_catastali: list[RiferimentoCatastale] = Field(default_factory=list)
    note_incertezza: list[str] = Field(default_factory=list)


class PreliminareCompravendita(BaseModel):
    """Il 'compromesso'. Confrontarlo con l'atto definitivo (quando disponibile)
    fa parte della due diligence: prezzo, caparra, condizioni sospensive e
    termini dichiarati qui devono essere coerenti con quanto poi rogitato."""

    CAMPI_ESSENZIALI: ClassVar[frozenset[str]] = frozenset(
        {"promittente_venditore", "promittente_acquirente", "prezzo_eur", "riferimenti_catastali", "condizioni_sospensive"}
    )

    tipo_documento: TipoDocumento = TipoDocumento.PRELIMINARE_COMPRAVENDITA
    collegamento_operazione: Optional[CollegamentoOperazione] = None
    condizioni_dettaglio: list[CondizioneContrattuale] = Field(default_factory=list)
    data: Optional[str] = None
    promittente_venditore: list[str] = Field(default_factory=list)
    promittente_acquirente: list[str] = Field(default_factory=list)
    prezzo_eur: Optional[CampoEstratto] = None
    caparra_eur: Optional[CampoEstratto] = None
    condizioni_sospensive: list[str] = Field(
        default_factory=list, description="es. ottenimento mutuo, assenza formalità pregiudizievoli"
    )
    termine_rogito: Optional[str] = None
    riferimenti_catastali: list[RiferimentoCatastale] = Field(default_factory=list)
    note_incertezza: list[str] = Field(default_factory=list)


class RelazioneTecnicaIntegrata(BaseModel):
    """Documento redatto da un tecnico abilitato (geometra, ingegnere,
    architetto) su incarico del venditore, dell'agente immobiliare o del
    notaio: verifica la conformità catastale e urbanistica dell'immobile
    (confronto tra titoli edilizi/planimetrie depositate e stato di fatto) e
    lo "stato legittimo" (art. 34-bis DPR 380/2001 su tolleranze costruttive).

    Non è obbligatoria per legge, ma è il documento con cui un agente
    immobiliare adempie concretamente all'obbligo di verifica/informazione
    ex art. 1759 c.c. (Cass. 24534/2022: il mediatore non può limitarsi alle
    dichiarazioni del venditore su conformità urbanistica/catastale — o
    verifica e comunica, o dichiara esplicitamente di non aver verificato).
    Fonti: notaiofacile.it su relazione tecnica integrata,
    biblus.acca.it su stato legittimo, studiotecnicopagliai.it su Cass. 24534/2022.
    """

    CAMPI_ESSENZIALI: ClassVar[frozenset[str]] = frozenset(
        {"riferimenti_catastali", "conformita_catastale", "conformita_urbanistica", "difformita_riscontrate"}
    )

    tipo_documento: TipoDocumento = TipoDocumento.RELAZIONE_TECNICA_INTEGRATA
    tecnico_redattore: Optional[str] = None
    tipo_tecnico: Optional[str] = Field(
        default=None, description="geometra, ingegnere, architetto, perito industriale edile"
    )
    data_relazione: Optional[str] = None
    destinazione_uso_legittima: Optional[CampoEstratto] = Field(default=None,
        description="Destinazione d’uso che il tecnico dichiara verificata, con citazione; non ricavarla dalla sola categoria catastale.")
    riferimenti_catastali: list[RiferimentoCatastale] = Field(default_factory=list)
    conformita_catastale: Optional[bool] = Field(
        default=None,
        description="True se la planimetria catastale depositata corrisponde allo stato di fatto rilevato",
    )
    conformita_urbanistica: Optional[bool] = Field(
        default=None,
        description="True se lo stato di fatto corrisponde ai titoli edilizi (permesso di costruire, SCIA, CILA...) esaminati",
    )
    stato_legittimo_verificato: Optional[bool] = Field(
        default=None, description="True se il tecnico ha potuto ricostruire e attestare lo stato legittimo dell'immobile"
    )
    difformita_riscontrate: list[str] = Field(
        default_factory=list,
        description="Ogni difformità/abuso segnalato dal tecnico, sanato o da sanare",
    )
    difformita_rientrano_in_tolleranza: Optional[bool] = Field(
        default=None,
        description="True se le difformità riscontrate rientrano nelle tolleranze costruttive art. 34-bis DPR 380/2001 (non richiedono sanatoria)",
    )
    titoli_edilizi_esaminati: list[str] = Field(default_factory=list)
    note_incertezza: list[str] = Field(default_factory=list)


class PeriziaDiStima(BaseModel):
    """Perizia di stima/valutazione dell'immobile, redatta da un perito
    tecnico (geometra, ingegnere, architetto) su incarico della banca
    erogante il mutuo, dell'agenzia immobiliare o del venditore. Determina il
    valore di riferimento che la banca usa per calcolare l'importo massimo
    finanziabile (loan-to-value, tipicamente fino all'80% del MINORE tra
    valore periziato e prezzo di acquisto): una perizia inferiore al prezzo
    pattuito riduce il mutuo erogabile e può far saltare la compravendita —
    un rischio molto concreto per l'agente che ha già trattato la vendita a
    quel prezzo. Fonti: mutui.it e idealista.it su perizia immobiliare e LTV.
    """

    CAMPI_ESSENZIALI: ClassVar[frozenset[str]] = frozenset(
        {"valore_stimato_eur", "riferimenti_catastali", "data_perizia"}
    )

    tipo_documento: TipoDocumento = TipoDocumento.PERIZIA_DI_STIMA
    perito: Optional[str] = None
    committente: Optional[str] = Field(
        default=None, description="Chi ha commissionato la perizia: banca, venditore, agenzia immobiliare"
    )
    finalita: Optional[str] = Field(
        default=None, description="es. 'erogazione mutuo', 'stima per vendita', 'perizia di parte'"
    )
    data_perizia: Optional[str] = None
    riferimenti_catastali: list[RiferimentoCatastale] = Field(default_factory=list)
    valore_stimato_eur: Optional[CampoEstratto] = None
    superficie_commerciale_considerata_mq: Optional[float] = None
    difformita_o_criticita_rilevate: list[str] = Field(
        default_factory=list,
        description="Eventuali difformità, criticità manutentive o fattori penalizzanti notati dal perito",
    )
    note_incertezza: list[str] = Field(default_factory=list)


# Registro che collega ogni TipoDocumento al suo modello Pydantic.
# Usato sia dall'estrattore (per sapere che schema applicare dopo la classificazione)
# sia dal consistency engine (per sapere quali campi sono comparabili tra due tipi).
SCHEMA_REGISTRY: dict[TipoDocumento, type[BaseModel]] = {
    TipoDocumento.ATTO_COMPRAVENDITA: AttoCompravendita,
    TipoDocumento.VISURA_CATASTALE: VisuraCatastale,
    TipoDocumento.APE: APE,
    TipoDocumento.CONTRATTO_LOCAZIONE: ContrattoLocazione,
    TipoDocumento.VISURA_IPOTECARIA: VisuraIpotecaria,
    TipoDocumento.PLANIMETRIA: Planimetria,
    TipoDocumento.CERTIFICATO_DESTINAZIONE_URBANISTICA: CertificatoDestinazioneUrbanistica,
    TipoDocumento.TITOLO_EDILIZIO: TitoloEdilizio,
    TipoDocumento.CERTIFICATO_AGIBILITA: CertificatoAgibilita,
    TipoDocumento.REGOLAMENTO_CONDOMINIO: RegolamentoCondominio,
    TipoDocumento.VERBALE_ASSEMBLEA_CONDOMINIO: VerbaleAssembleaCondominio,
    TipoDocumento.DICHIARAZIONE_CONFORMITA_IMPIANTI: DichiarazioneConformitaImpianti,
    TipoDocumento.ATTO_DI_PROVENIENZA: AttoDiProvenienza,
    TipoDocumento.PRELIMINARE_COMPRAVENDITA: PreliminareCompravendita,
    TipoDocumento.RELAZIONE_TECNICA_INTEGRATA: RelazioneTecnicaIntegrata,
    TipoDocumento.PERIZIA_DI_STIMA: PeriziaDiStima,
    TipoDocumento.LICENZA_COMMERCIALE: LicenzaCommerciale,
    TipoDocumento.CERTIFICATO_PREVENZIONE_INCENDI: CertificatoPrevenzioneIncendi,
    TipoDocumento.VISURA_CAMERALE: VisuraCamerale,
}


# ---------------------------------------------------------------------------
# Modelli di supporto per classificazione e verifica (non sono "documenti",
# ma output strutturati di altri passaggi della pipeline).
# ---------------------------------------------------------------------------


class ClassificationResult(BaseModel):
    tipo_documento: TipoDocumento
    confidence: float = Field(ge=0.0, le=1.0)
    motivazione: str = Field(description="Breve motivazione della classificazione (1-2 frasi)")


class CampoNonSupportato(BaseModel):
    campo: str = Field(description="Nome del campo (dot-path) che non risulta supportato dal testo")
    valore_estratto: str = Field(description="Il valore che era stato estratto per quel campo")
    motivo: str = Field(
        description="Perché il valore non è supportato: non presente, dedotto, in contraddizione col testo, ecc."
    )
    gravita: str = Field(description="'bassa', 'media' o 'alta'")


class VerificationResult(BaseModel):
    """Esito del passaggio di verifica (grounding check) sull'estrazione.

    Questo è il secondo passaggio della catena extract -> verify: un modello
    (idealmente chiamato a temperatura 0 e senza vedere il proprio output
    precedente come "verità già accettata") rilegge il documento originale e i
    dati estratti, e segnala ogni campo che NON trova effettivamente supportato
    dal testo. È la tecnica di "chain-of-verification" per ridurre le
    allucinazioni nell'estrazione strutturata.
    """

    tutti_i_campi_supportati: bool
    campi_non_supportati: list[CampoNonSupportato] = Field(default_factory=list)
    osservazioni_generali: Optional[str] = None


# ---------------------------------------------------------------------------
# Tiering dei campi: "essenziali" (super necessari) vs "accessori".
#
# Ogni modello documento sopra dichiara un CAMPI_ESSENZIALI: ClassVar[frozenset[str]]
# — i nomi dei campi (top-level) senza i quali il documento non è utilizzabile
# ai fini della due diligence: o perché sono elementi essenziali del negozio
# giuridico (essentialia negotii), o perché sono richiesti per legge/prassi per
# quel tipo di certificato/atto, o perché alimentano direttamente un controllo
# automatico (consistency engine / red_flags). Le fonti puntuali sono citate
# nel docstring di ciascun modello.
#
# Tutti gli altri campi "di dato" (cioè non presenti in _CAMPI_META, che sono
# metadati di pipeline e non vengono mai tierati) sono "accessori": vanno
# comunque estratti e salvati quando presenti nel documento (arricchiscono il
# fascicolo ed possono comunque servire, es. in una scansione RAG o per una
# domanda specifica dell'utente), ma la loro assenza non blocca né declassa
# grave la due diligence, e non vengono segnalati come "informazione mancante"
# con la stessa urgenza dei campi essenziali. CampoEstratto usa ClassVar
# apposta per essere invisibile allo schema JSON passato all'API (l'estrattore
# tenta comunque di estrarre TUTTI i campi del modello, essenziali e accessori:
# il tiering è usato a valle, per dare priorità/gravità al missing-info
# detection, non per limitare cosa viene estratto).
def campi_essenziali(model_cls: type[BaseModel]) -> frozenset[str]:
    """Nomi dei campi "super necessari" dichiarati dal modello, o insieme vuoto
    se il modello non definisce un tiering esplicito (es. i modelli di supporto
    come ClassificationResult, non essendo "documenti")."""

    return getattr(model_cls, "CAMPI_ESSENZIALI", frozenset())


def campi_accessori(model_cls: type[BaseModel]) -> frozenset[str]:
    """Tutti i campi "di dato" del modello che non sono né essenziali né
    metadati di pipeline (tipo_documento, note_incertezza): campi che vanno
    comunque estratti e salvati, ma che non sono prioritari nel missing-info
    detection."""

    tutti_i_campi = frozenset(model_cls.model_fields.keys())
    return tutti_i_campi - campi_essenziali(model_cls) - _CAMPI_META


