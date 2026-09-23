"""
Catalogo di criticità (red flag) deterministiche per la due diligence immobiliare.

Questo è il pezzo che rende il sistema "verticale su qualsiasi caso possibile":
non si limita a confrontare due numeri tra loro (quello lo fa consistency.py),
ma applica conoscenza normativa e di prassi del settore immobiliare italiano
per riconoscere situazioni note per essere problematiche — provenienza
donativa, formalità pregiudizievoli attive, assenza di titoli edilizi o di
agibilità, vincoli condominiali, spese straordinarie deliberate prima del
rogito, ecc.

Ogni funzione check_* è documentata con la fonte su cui si basa la regola (le
principali sono citate anche nel README). Sono controlli DETERMINISTICI su
dati già estratti: non fanno chiamate LLM, quindi sono economici, veloci e
riproducibili al 100% — la parte "interpretativa" più aperta (es. leggere una
clausola insolita nel testo libero di un atto) è invece compito del passaggio
di revisione LLM in due_diligence.py, che ha accesso al testo integrale via
RAG e non solo ai campi strutturati.

Questo catalogo NON sostituisce un parere legale/notarile: è pensato per
segnalare all'utente COSA verificare con un professionista, non per dare un
giudizio legale definitivo (coerentemente con la regola 3 del system prompt).
"""

from __future__ import annotations

from observability import Identifiable

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from consistency import _riferimenti_coincidono
from fascicolo import Fascicolo


@dataclass
class RedFlag(Identifiable):
    categoria: str
    titolo: str
    gravita: str  # "bassa" | "media" | "alta" | "critica"
    descrizione: str
    riferimento: Optional[str] = None  # norma/prassi su cui si basa
    azione_consigliata: Optional[str] = None
    fonte: str = "regola_deterministica"  # vs "analisi_llm" nel report finale


def _parse_data(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Provenienza: donazione, successione
# ---------------------------------------------------------------------------

def check_provenienza_donativa(fascicolo: Fascicolo, oggi: Optional[date] = None) -> list[RedFlag]:
    """Provenienza donativa: rischio di azione di riduzione/restituzione.

    Fonte: art. 553 ss. c.c.; l'azione di riduzione è esperibile dai
    legittimari lesi entro 10 anni dall'apertura della successione del
    donante, l'azione di restituzione contro il terzo acquirente (il tuo
    cliente) entro 20 anni dalla trascrizione della donazione. Le banche sono
    tipicamente restie a concedere mutui su questi immobili perché in caso di
    restituzione l'immobile tornerebbe ai legittimari libero da ipoteche.

    Soluzioni di prassi, in ordine di frequenza d'uso: (1) risoluzione
    consensuale della donazione originaria tra donante e donatario, seguita
    da nuovo atto di trasferimento non donativo, quando il donante è ancora
    in vita e disponibile; (2) rinuncia formale all'azione da parte di TUTTI
    i legittimari (richiede la loro individuazione completa ed è quindi
    delicata se la famiglia è numerosa o i rapporti sono tesi); (3) — la più
    usata quando le prime due non sono praticabili — una polizza
    assicurativa "donazione sicura": copre il valore di mercato
    dell'immobile in caso di azione di riduzione/restituzione vittoriosa
    (il legittimario viene soddisfatto in denaro dall'assicurazione, non
    riottiene l'immobile), dura fino a 20 anni dalla donazione (lo stesso
    termine di decadenza dell'azione), il massimale è calcolato sul valore
    commerciale dichiarato, e — punto rilevante per un agente — la polizza
    si trasferisce automaticamente al successivo acquirente in caso di
    rivendita, senza costi aggiuntivi, ed è quindi un argomento di vendita
    per l'immobile stesso. Fonte sulla polizza: rockagent.it — assicurazione
    donazione sicura.
    """
    prov = fascicolo.atto_provenienza
    if not prov or not prov.tipo_provenienza:
        return []
    if "donazion" not in prov.tipo_provenienza.lower():
        return []

    oggi = oggi or date.today()
    data_donazione = _parse_data(prov.data_atto)
    dettaglio_tempo = ""
    gravita = "alta"
    if data_donazione:
        anni_trascorsi = (oggi - data_donazione).days / 365.25
        anni_rimanenti = max(0.0, 20 - anni_trascorsi)
        if anni_rimanenti <= 0:
            gravita = "media"
            dettaglio_tempo = (
                f" Sono trascorsi oltre 20 anni dalla trascrizione ({anni_trascorsi:.0f} anni): "
                "il rischio di azione di restituzione contro l'acquirente è normalmente estinto, "
                "ma va comunque verificato con un notaio caso per caso (es. sospensioni del termine)."
            )
        else:
            dettaglio_tempo = (
                f" Sono trascorsi circa {anni_trascorsi:.0f} anni dalla trascrizione della donazione: "
                f"mancano indicativamente {anni_rimanenti:.0f} anni al termine ventennale."
            )

    return [
        RedFlag(
            categoria="provenienza",
            titolo="Provenienza donativa",
            gravita=gravita,
            descrizione=(
                "L'immobile proviene da una donazione. Gli eredi legittimari lesi nella loro quota "
                "possono agire in riduzione entro 10 anni dalla morte del donante e, se il bene è "
                "stato ceduto a terzi, in restituzione contro l'acquirente entro 20 anni dalla "
                "trascrizione della donazione — l'immobile tornerebbe ai legittimari libero da "
                "ipoteche. Per questo le banche sono spesso restie a concedere mutui su questi "
                "immobili senza garanzie accessorie." + dettaglio_tempo
            ),
            riferimento="Art. 553 e ss. c.c. (azione di riduzione e restituzione)",
            azione_consigliata=(
                "Valutare con un notaio, in ordine di praticabilità: risoluzione consensuale della "
                "donazione (se il donante è vivo e disponibile), rinuncia formale all'azione da parte "
                "di TUTTI i legittimari, o — soluzione più comune quando le prime due non sono "
                "praticabili — una polizza 'donazione sicura' (copre il valore dell'immobile fino a 20 "
                "anni dalla donazione e si trasferisce automaticamente a un futuro acquirente)."
            ),
        )
    ]


def check_successione_non_divisa(fascicolo: Fascicolo) -> list[RedFlag]:
    """Provenienza da successione non ancora divisa tra i coeredi: l'immobile è
    in comunione ereditaria, quindi la vendita richiede il consenso di TUTTI i
    coeredi (o un atto di divisione preliminare); manca spesso dal fascicolo
    la lista completa dei coeredi.
    """
    prov = fascicolo.atto_provenienza
    if not prov or not prov.tipo_provenienza or "success" not in prov.tipo_provenienza.lower():
        return []
    if prov.successione_divisa is True:
        return []
    return [
        RedFlag(
            categoria="provenienza",
            titolo="Successione non risulta divisa",
            gravita="alta" if prov.successione_divisa is False else "media",
            descrizione=(
                "L'immobile proviene da una successione e non risulta (o non è chiaro se) "
                "l'eredità sia stata divisa tra i coeredi. Se l'immobile è ancora in comunione "
                "ereditaria, la vendita richiede il consenso di TUTTI i coeredi, non solo del "
                "venditore che compare nell'atto."
            ),
            riferimento="Comunione ereditaria, artt. 713 ss. c.c.",
            azione_consigliata="Verificare l'elenco completo dei coeredi e che tutti partecipino all'atto o abbiano già diviso/ceduto le proprie quote.",
        )
    ]


def check_diritto_abitazione_coniuge_superstite(fascicolo: Fascicolo) -> list[RedFlag]:
    """Diritto di abitazione del coniuge superstite (art. 540, comma 2, c.c.)
    su un immobile proveniente da successione — un "caso particolare" che
    nessuna visura mostra in modo affidabile.

    Quando il defunto (dante_causa dell'atto di provenienza) era coniugato o
    in unione civile al momento del decesso, la legge attribuisce
    automaticamente al coniuge/unito civilmente superstite un diritto di
    abitazione VITALIZIO sulla casa che era effettivamente adibita a
    residenza familiare (non basta la residenza anagrafica) — un legato ex
    lege che nasce all'apertura della successione, non un'attribuzione
    discrezionale del testamento o della divisione tra coeredi.

    Il punto che rende questo rischio particolarmente insidioso per la due
    diligence: è opponibile a un futuro acquirente ANCHE SENZA trascrizione,
    perché nasce direttamente dalla legge — la Cassazione lo ha confermato
    più volte (ord. 4092/2023, tra le altre) chiarendo che l'art. 2644 c.c.
    sulla trascrizione non si applica qui, perché erede e coniuge superstite
    acquisiscono diritti diversi e non in conflitto tra loro dallo stesso
    defunto. Significa che un acquirente non può fare affidamento su una
    visura ipotecaria "pulita" per escludere questo rischio: l'unico modo
    per scoprirlo è leggere con attenzione l'atto di provenienza e la
    dichiarazione di successione. È inoltre un diritto AUTONOMO rispetto
    alla qualità di erede: un coniuge superstite che rinuncia all'eredità
    NON perde per questo il diritto di abitazione, quindi la sua assenza tra
    gli eredi che vendono non è di per sé rassicurante.

    Gravità "alta": un diritto di abitazione vitalizio può rendere
    l'immobile sostanzialmente inutilizzabile per l'acquirente per tutta la
    vita del coniuge superstite — un impatto pratico paragonabile a una
    formalità pregiudizievole seria, anche se giuridicamente è cosa diversa
    da un'ipoteca o un pignoramento.

    Limite noto: il controllo guarda solo all'atto di provenienza più
    recente (un livello), come il resto del sistema — una catena di
    successioni/vendite più lunga richiederebbe ricostruire la provenienza
    su più livelli, cosa che questo prototipo non fa.

    Fonti: [Notaio Torino — il diritto di abitazione del coniuge superstite
    sulla casa
    familiare](https://blog.notaiotorino.org/diritto-di-abitazione-coniuge-superstite/);
    [Casa & Associati — il diritto di abitazione del coniuge del de cuius è
    opponibile ai terzi anche in assenza di
    trascrizione](https://casaeassociati.it/il-diritto-di-abitazione-del-coniuge-del-de-cuius-e-opponibile-ai-terzi-anche-in-assenza-di-trascrizione/)
    (cita Cass. 4092/2023, 15667/2019, 8400/2019, 18354/2013, 7128/2023).
    """
    prov = fascicolo.atto_provenienza
    if not prov or not prov.tipo_provenienza or "success" not in prov.tipo_provenienza.lower():
        return []
    if prov.coniuge_superstite_presente is not True:
        return []
    if prov.diritto_abitazione_coniuge_rinunciato is True:
        return []
    return [
        RedFlag(
            categoria="provenienza",
            titolo="Possibile diritto di abitazione del coniuge superstite non risolto",
            gravita="alta",
            descrizione=(
                "L'atto di provenienza indica che il defunto era coniugato (o in unione civile) al "
                "momento del decesso. Se l'immobile era effettivamente adibito a residenza familiare, "
                "la legge attribuisce al coniuge superstite un diritto di abitazione vitalizio (art. "
                "540, comma 2, c.c.), opponibile a un futuro acquirente ANCHE SENZA trascrizione: non "
                "basta una visura ipotecaria pulita per escludere questo rischio. Il diritto è inoltre "
                "autonomo dalla qualità di erede: anche se il coniuge superstite ha rinunciato "
                "all'eredità o non compare tra i venditori, potrebbe comunque conservarlo."
            ),
            riferimento="Art. 540, comma 2, c.c.; Cass. 4092/2023 e giurisprudenza conforme (opponibilità senza trascrizione)",
            azione_consigliata=(
                "Verificare con gli eredi/il notaio: se l'immobile era davvero la residenza familiare "
                "effettiva del defunto (non basta la residenza anagrafica); se il coniuge superstite è "
                "ancora in vita; e soprattutto se ha reso una rinuncia FORMALE e specifica al diritto "
                "di abitazione (atto notarile dedicato, non la sola rinuncia all'eredità). Senza questa "
                "rinuncia specifica, non dare per risolto il rischio anche se il coniuge non compare "
                "nell'atto."
            ),
        )
    ]


def _regime_indica_comunione_senza_esclusione(regime: Optional[str]) -> bool:
    """True se il testo dichiarato indica comunione legale dei beni SENZA una
    dichiarazione di esclusione (bene personale ex art. 179 c.c.) e senza
    indicare separazione dei beni. Un semplice controllo di substring è
    volutamente conservativo: se il campo è ambiguo o assente, non scatta
    (coerente con la regola 'non inventare mai un dato' — qui si traduce in
    'non presumere mai mancanza di un vincolo che non risulta dal testo')."""
    if not regime:
        return False
    r = regime.lower()
    if "comunione" not in r:
        return False
    if "separazione" in r:
        return False
    if "personale" in r or "179" in r or "escluso dalla comunione" in r:
        return False
    return True


def check_comunione_legale_coniuge_non_intervenuto(fascicolo: Fascicolo) -> list[RedFlag]:
    """Comunione legale dei beni e coniuge non intervenuto nell'atto.

    In Italia il regime patrimoniale legale tra coniugi, in mancanza di
    diversa convenzione, è la comunione dei beni (art. 159 c.c.): un
    immobile acquistato da un solo coniuge durante il matrimonio in questo
    regime diventa comunque comproprietà di ENTRAMBI i coniugi per effetto
    di legge (art. 177 c.c.), anche se il coniuge "non firmatario" non
    compare affatto nell'atto d'acquisto. Fanno eccezione i beni personali
    elencati dall'art. 179 c.c. (tra cui quelli acquistati col ricavato
    della vendita di un bene personale), ma per gli immobili l'esclusione è
    opponibile a terzi solo se dichiarata espressamente nell'atto CON LA
    PARTECIPAZIONE dell'altro coniuge.

    Se un atto (di vendita attuale o di provenienza) dichiara un regime di
    comunione legale ma un solo coniuge vi compare, senza menzionare
    un'esclusione ex art. 179 c.c., l'atto è annullabile su richiesta del
    coniuge escluso entro un anno dalla conoscenza dell'atto, dalla sua
    trascrizione (se anteriore), o dallo scioglimento della comunione se
    l'atto non fu trascritto (art. 184 c.c.) — quindi non è un vizio che
    "si sana da solo" col tempo breve, e nel frattempo la provenienza del
    tuo cliente resta esposta. Una regola professionale del notariato
    (Consiglio Notarile, "Regola n. 5 sull'accertamento dei regimi
    patrimoniali") segnala inoltre che la sola dichiarazione di parte non è
    considerata una verifica affidabile in questa materia, proprio perché
    l'unico riscontro oggettivo è l'annotazione a margine dell'atto di
    matrimonio (complicata da matrimoni celebrati all'estero o da regimi
    non annotati) — per questo l'azione consigliata non si limita a
    "chiedere conferma al venditore".

    Il controllo è deliberatamente conservativo: scatta SOLO quando il
    fascicolo contiene una dichiarazione esplicita di regime di comunione
    (mai per assenza di menzione, che qui significherebbe presumere un
    vincolo che il testo non attesta) e un solo coniuge risulta parte.

    Fonti: art. 159, 177, 179, 184 c.c.; [Cosso Immobiliare — la comunione
    legale dei beni e gli acquisti immobiliari](https://www.cossoimmobiliare.it/la-comunione-legale-dei-beni-gli-acquisti-immobiliari/);
    [Consiglio Notarile — Regola n. 5 sull'accertamento dei regimi
    patrimoniali](https://www.notaio.org/files/regola_n5_accertamento_dei_regimi_matrimoniali.pdf).
    """
    flags: list[RedFlag] = []

    atto = fascicolo.atto_compravendita
    if (
        atto
        and _regime_indica_comunione_senza_esclusione(atto.regime_patrimoniale_dichiarato)
        and len(atto.parte_venditrice) == 1
    ):
        flags.append(
            RedFlag(
                categoria="provenienza",
                titolo="Regime di comunione legale dichiarato ma un solo coniuge risulta venditore",
                gravita="alta",
                descrizione=(
                    f"L'atto dichiara il regime di comunione legale dei beni per il venditore "
                    f"({atto.regime_patrimoniale_dichiarato!r}), ma compare come parte venditrice "
                    "solo una persona. Se l'immobile è stato acquistato durante il matrimonio in "
                    "questo regime (e non rientra nei beni personali ex art. 179 c.c.), il coniuge "
                    "non firmatario è comunque comproprietario per legge (art. 177 c.c.) e il suo "
                    "consenso a QUESTA vendita è necessario: in sua assenza l'atto è annullabile su "
                    "richiesta del coniuge escluso entro un anno dalla conoscenza dell'atto o dalla "
                    "trascrizione."
                ),
                riferimento="Artt. 159, 177, 179, 184 c.c.",
                azione_consigliata=(
                    "Non limitarsi alla dichiarazione verbale del venditore: richiedere l'estratto "
                    "per riassunto dell'atto di matrimonio (con le eventuali annotazioni sul regime) "
                    "e far intervenire il coniuge come co-venditore o farne acquisire il consenso "
                    "espresso, salvo che risulti una valida esclusione ex art. 179 c.c. per questo "
                    "immobile."
                ),
            )
        )

    prov = fascicolo.atto_provenienza
    if (
        prov
        and prov.tipo_provenienza
        and "success" not in prov.tipo_provenienza.lower()
        and "donaz" not in prov.tipo_provenienza.lower()
        and _regime_indica_comunione_senza_esclusione(prov.regime_patrimoniale_dichiarato)
        and len(prov.avente_causa) == 1
    ):
        flags.append(
            RedFlag(
                categoria="provenienza",
                titolo="Possibile comproprietà del coniuge non risultante nell'atto di provenienza",
                gravita="alta",
                descrizione=(
                    "L'atto di provenienza dichiara che l'attuale venditore ha acquistato "
                    f"l'immobile in regime di comunione legale dei beni "
                    f"({prov.regime_patrimoniale_dichiarato!r}), ma vi compare come acquirente solo "
                    "questa persona. Per effetto dell'art. 177 c.c. il coniuge può essere "
                    "comproprietario automatico dell'immobile ancora oggi, anche se non è mai "
                    "comparso in alcun atto: se così fosse, il venditore attuale non potrebbe "
                    "trasferire da solo la piena proprietà nella vendita che stai seguendo."
                ),
                riferimento="Artt. 159, 177, 179 c.c.",
                azione_consigliata=(
                    "Verificare lo stato civile attuale del venditore e, se all'epoca dell'acquisto "
                    "era coniugato in comunione legale, richiedere l'estratto per riassunto dell'atto "
                    "di matrimonio per accertare se il coniuge risulta ancora comproprietario: in tal "
                    "caso deve intervenire anche lui/lei nell'atto di vendita attuale come venditore."
                ),
            )
        )

    return flags


def check_decadenza_prima_casa_venditore(fascicolo: Fascicolo, oggi: Optional[date] = None) -> list[RedFlag]:
    """Rivendita infraquinquennale con rischio di decadenza dalle
    agevolazioni "prima casa" per il VENDITORE (non per l'acquirente).

    Chi acquista un immobile con le agevolazioni prima casa (imposta di
    registro al 2% invece del 9% ordinario, o IVA al 4% invece del 10%) deve
    mantenerlo per almeno 5 anni: se lo rivende prima e non riacquista
    un'altra prima casa entro un anno dalla vendita, decade dal beneficio.
    La decadenza comporta il recupero della differenza d'imposta (7 punti
    per il registro, 6 per l'IVA), una sovrattassa del 30% su quella
    differenza, più gli interessi di mora — un costo che grava sul
    VENDITORE attuale, non sull'acquirente che stai seguendo in questa
    transazione, ma che può comunque incidere sulla trattativa: un venditore
    che scopre solo a ridosso del rogito di dover affrontare questo costo,
    o che deve chiudere un riacquisto entro l'anno per evitarlo, ha un
    incentivo (o un vincolo di tempo) che un agente informato può gestire
    meglio di uno colto di sorpresa.

    Il controllo guarda all'atto di PROVENIENZA (come l'attuale venditore ha
    acquistato l'immobile), non all'atto attuale: se lì risulta dichiarato
    che l'acquisto beneficiò delle agevolazioni prima casa, e da quella data
    non sono ancora trascorsi 5 anni, il rischio è concreto. Limitato al
    caso "provenienza per compravendita" (le agevolazioni prima casa
    riguardano acquisti a titolo oneroso).

    Fonti: [Agenzia delle Entrate — l'acquisto con i benefici prima
    casa](https://www.agenziaentrate.gov.it/portale/l-acquisto-con-i-benefici-prima-casa);
    [Notaio Torino — agevolazioni prima casa, guida
    completa](https://blog.notaiotorino.org/agevolazioni-prima-casa/); [Fiscomania —
    sanzione decadenza agevolazione prima casa](https://fiscomania.com/sanzione-decadenza-agevolazione-prima-casa/).
    """
    prov = fascicolo.atto_provenienza
    if not prov or not prov.tipo_provenienza or "compravendita" not in prov.tipo_provenienza.lower():
        return []
    if prov.agevolazioni_prima_casa_dichiarate is not True:
        return []

    oggi = oggi or date.today()
    data_acquisto = _parse_data(prov.data_atto)
    if not data_acquisto:
        return []
    anni_trascorsi = (oggi - data_acquisto).days / 365.25
    if anni_trascorsi >= 5:
        return []
    anni_rimanenti = 5 - anni_trascorsi

    return [
        RedFlag(
            categoria="provenienza",
            titolo="Possibile decadenza dalle agevolazioni prima casa per il venditore",
            gravita="media",
            descrizione=(
                "L'atto di provenienza dichiara che l'attuale venditore acquistò l'immobile con le "
                f"agevolazioni prima casa circa {anni_trascorsi:.1f} anni fa: mancano indicativamente "
                f"{anni_rimanenti:.1f} anni al termine dei 5 anni previsti. Se la vendita che stai "
                "seguendo si perfeziona ora e il venditore non ha già riacquistato (o non riacquista "
                "entro un anno dalla vendita) un'altra prima casa, decade dal beneficio: recupero della "
                "differenza d'imposta (7 punti percentuali per il registro, 6 per l'IVA), sovrattassa "
                "del 30% su quella differenza, più interessi di mora — un costo del venditore, non "
                "dell'acquirente, ma che può influire sulla trattativa o sui tempi che il venditore "
                "chiede per chiudere."
            ),
            riferimento="Nota II-bis, art. 1 Tariffa Parte I, D.P.R. 131/1986 (Testo Unico Imposta di Registro)",
            azione_consigliata=(
                "Chiedere al venditore se ha già individuato o riacquistato un'altra prima casa: se sì, "
                "verificare che il riacquisto rientri (o rientrerà) nel termine di un anno dalla vendita "
                "attuale. Se no, informarlo del costo potenziale (recupero imposta + sovrattassa 30% + "
                "interessi) prima del rogito, così può valutarlo nella trattativa invece di scoprirlo dopo."
            ),
        )
    ]


# ---------------------------------------------------------------------------
# Formalità pregiudizievoli (ipoteche, pignoramenti)
# ---------------------------------------------------------------------------

def check_formalita_pregiudizievoli(fascicolo: Fascicolo) -> list[RedFlag]:
    """Ipoteche/pignoramenti/sequestri ancora attivi sull'immobile.

    Nota di calibrazione: un'ipoteca VOLONTARIA a garanzia del mutuo con cui il
    venditore ha comprato l'immobile è una situazione comune e gestibile (si
    estingue al rogito con il ricavato della vendita, spesso con contestuale
    atto di assenso alla cancellazione o surroga) — non è di per sé allarmante.
    Pignoramenti e sequestri (formalità giudiziali che indicano una procedura
    esecutiva o cautelare in corso) sono invece molto più gravi: l'immobile
    potrebbe non essere liberamente disponibile alla vendita.
    """
    flags = []
    for v in fascicolo.visure_ipotecarie:
        if v.formalita_ancora_attiva is False:
            continue  # esplicitamente cancellata: nessun rischio
        tipo = (v.tipo_formalita or "").lower()
        if "pignorament" in tipo or "sequestr" in tipo:
            flags.append(
                RedFlag(
                    categoria="formalita_pregiudizievoli",
                    titolo=f"{v.tipo_formalita or 'Formalità giudiziale'} sull'immobile",
                    gravita="critica",
                    descrizione=(
                        f"Risulta una formalità di tipo '{v.tipo_formalita}' "
                        f"{'ancora attiva' if v.formalita_ancora_attiva else 'la cui cancellazione non è confermata'}. "
                        "Questo tipo di formalità indica tipicamente una procedura esecutiva o "
                        "cautelare in corso: l'immobile potrebbe non essere liberamente "
                        "disponibile alla vendita senza autorizzazione del giudice/creditore procedente."
                    ),
                    riferimento="Procedure esecutive/cautelari, c.p.c.",
                    azione_consigliata="Non procedere senza parere legale specifico; verificare lo stato della procedura presso il tribunale competente.",
                )
            )
        elif "ipoteca" in tipo:
            flags.append(
                RedFlag(
                    categoria="formalita_pregiudizievoli",
                    titolo="Ipoteca sull'immobile",
                    gravita="media",
                    descrizione=(
                        f"Risulta un'ipoteca ({v.tipo_formalita}) "
                        f"{'attiva' if v.formalita_ancora_attiva else 'la cui cancellazione non è confermata'}"
                        f"{f' a garanzia di un finanziamento di {v.ente_creditore}' if v.ente_creditore else ''}. "
                        "Se è a garanzia del mutuo del venditore, è una situazione comune, gestibile "
                        "in sede di rogito con il ricavato della vendita — ma va sempre verificato "
                        "l'importo residuo e le modalità di cancellazione/assenso."
                    ),
                    riferimento="Ipoteca volontaria/giudiziale, artt. 2808 ss. c.c.",
                    azione_consigliata=(
                        "Chiedere l'importo residuo del debito garantito e le modalità di "
                        "cancellazione contestuale al rogito — non fidarsi della sola dichiarazione "
                        "verbale del venditore che il debito è estinto: in un caso concreto di due "
                        "diligence documentato (mbg.legal) un'ipoteca risultava ancora iscritta "
                        "nonostante il venditore affermasse di averla già estinta, ed è stata "
                        "richiesta la cancellazione formale dell'iscrizione prima della stipula "
                        "definitiva proprio perché la sola parola del venditore non basta a "
                        "escludere il vincolo per un futuro acquirente/rivenditore."
                    ),
                )
            )
        else:
            flags.append(
                RedFlag(
                    categoria="formalita_pregiudizievoli",
                    titolo="Formalità pregiudizievole da verificare",
                    gravita="media",
                    descrizione=f"Risulta una formalità ('{v.tipo_formalita or 'tipo non specificato'}') di cui non è confermata la cancellazione.",
                    azione_consigliata="Chiarire natura e stato della formalità con la visura ipotecaria aggiornata.",
                )
            )
    return flags


# ---------------------------------------------------------------------------
# Conformità catastale e urbanistica
# ---------------------------------------------------------------------------

def check_conformita_catastale_mancante(fascicolo: Fascicolo) -> list[RedFlag]:
    """L'atto di compravendita deve contenere il riferimento alle planimetrie
    catastali e la dichiarazione di conformità allo stato di fatto (o
    un'attestazione tecnica sostitutiva): in assenza, l'atto è nullo.

    Fonte: art. 29, comma 1-bis, L. 52/1985 (introdotto da L. 122/2010).
    """
    atto = fascicolo.atto_compravendita
    if not atto:
        return []
    ha_planimetria = fascicolo.planimetria is not None
    menzione_conformita = any(
        "conformità catastale" in c.lower() or "conformita' catastale" in c.lower()
        for c in atto.clausole_rilevanti
    )
    if ha_planimetria and menzione_conformita:
        return []
    mancanti = []
    if not ha_planimetria:
        mancanti.append("planimetria catastale")
    if not menzione_conformita:
        mancanti.append("dichiarazione di conformità catastale nell'atto")
    return [
        RedFlag(
            categoria="conformita_catastale",
            titolo="Dichiarazione di conformità catastale non verificabile",
            gravita="alta",
            descrizione=(
                "Non risulta nel fascicolo: " + ", ".join(mancanti) + ". L'atto di compravendita deve "
                "contenere il riferimento alle planimetrie depositate in catasto e la dichiarazione, "
                "resa dal venditore o da un tecnico abilitato, che lo stato di fatto dell'immobile "
                "corrisponde ai dati catastali: in assenza, l'atto è nullo."
            ),
            riferimento="Art. 29, comma 1-bis, L. 52/1985 (introdotto da L. 122/2010)",
            azione_consigliata="Richiedere la planimetria catastale aggiornata e la dichiarazione di conformità (o incaricare un tecnico per la verifica) prima del rogito.",
        )
    ]


def check_titolo_edilizio_mancante(fascicolo: Fascicolo) -> list[RedFlag]:
    """Assenza di titoli edilizi nel fascicolo: impossibile verificare la
    conformità urbanistica ('stato legittimo') dell'immobile, concetto
    distinto dalla conformità catastale. Un immobile con abusi edilizi non
    sanati può essere difficilmente commerciabile ('aliud pro alio' in caso di
    abusi rilevanti) o esporre l'acquirente a sanzioni.
    """
    if fascicolo.tipo_transazione != "acquisto":
        return []
    if not fascicolo.atto_compravendita and not fascicolo.preliminare_compravendita:
        return []
    if fascicolo.titoli_edilizi:
        return []
    return [
        RedFlag(
            categoria="conformita_urbanistica",
            titolo="Titoli edilizi non presenti nel fascicolo",
            gravita="media",
            descrizione=(
                "Non risultano titoli edilizi (permesso di costruire, CILA, SCIA, licenza edilizia "
                "storica) nel fascicolo. Senza questi documenti non è possibile verificare lo 'stato "
                "legittimo' dell'immobile, cioè che quanto costruito corrisponda a un titolo "
                "abilitativo valido: un abuso edilizio non sanato può rendere l'immobile difficilmente "
                "commerciabile o esporre l'acquirente a conseguenze sanzionatorie."
            ),
            riferimento="Testo Unico Edilizia (DPR 380/2001); concetto di 'stato legittimo'",
            azione_consigliata="Richiedere al venditore la sequenza dei titoli edilizi e, se necessario, incaricare un tecnico per l'accesso agli atti comunali.",
        )
    ]


# ---------------------------------------------------------------------------
# Agibilità
# ---------------------------------------------------------------------------

def check_agibilita_mancante(fascicolo: Fascicolo) -> list[RedFlag]:
    """Assenza del certificato di agibilità: non rende nullo l'atto, ma può
    costituire un vizio della cosa venduta con conseguenze risarcitorie (o,
    nei casi più gravi di violazioni insanabili che rendono l'immobile
    oggettivamente inidoneo all'uso, motivo di risoluzione del contratto)."""
    if fascicolo.tipo_transazione != "acquisto":
        return []
    if not fascicolo.atto_compravendita and not fascicolo.preliminare_compravendita:
        return []
    if fascicolo.agibilita:
        return []
    return [
        RedFlag(
            categoria="agibilita",
            titolo="Certificato di agibilità non presente nel fascicolo",
            gravita="media",
            descrizione=(
                "Non risulta il certificato di agibilità. Non ne consegue automaticamente la nullità "
                "dell'atto, ma la giurisprudenza lo tratta come un possibile vizio della cosa venduta: "
                "se le violazioni sono sanabili, il rimedio tipico è il risarcimento del danno; se sono "
                "irrimediabili e rendono l'immobile oggettivamente inidoneo all'uso previsto, può "
                "portare alla risoluzione del contratto."
            ),
            riferimento="Art. 24-25 DPR 380/2001; giurisprudenza di legittimità su vizi della cosa venduta",
            azione_consigliata="Richiedere il certificato di agibilità o, in sua assenza, chiarire nel preliminare/atto chi si assume la responsabilità di ottenerlo e con quali garanzie.",
        )
    ]


# ---------------------------------------------------------------------------
# Impianti
# ---------------------------------------------------------------------------

def check_conformita_impianti_assente(fascicolo: Fascicolo) -> list[RedFlag]:
    """Dichiarazione di conformità degli impianti (elettrico, idraulico, gas,
    termico), ex D.M. 37/2008 (che ha sostituito la L. 46/90).

    A differenza di agibilità e conformità catastale, la conformità degli
    impianti NON incide sulla validità/commerciabilità dell'atto: la
    compravendita è comunque valida anche senza. È però un elemento di
    rischio pratico concreto per la trattativa — "la mancanza di
    documentazione può rendere difficile la vendita o la locazione", poiché
    acquirenti e conduttori la richiedono come prova di sicurezza — e la
    mancata dichiarazione da parte dell'installatore è sanzionata (100-1.000 €
    a seconda della complessità dell'impianto, con segnalazione alla Camera
    di Commercio). Per impianti installati prima del 13 marzo 1990 la
    dichiarazione non può essere pretesa (norma non ancora in vigore
    all'epoca dell'installazione).

    Gravità "bassa" se il documento manca del tutto dal fascicolo (situazione
    comune e spesso recuperabile), "media" se il documento è presente ma
    dichiara l'impianto NON conforme (richiede messa a norma o accollo
    esplicito di responsabilità da parte dell'acquirente).

    Fonti: [idealista.it — mancata consegna della dichiarazione di
    conformità impianti, cosa succede](https://www.idealista.it/news/finanza/casa/2024/05/20/180897-mancata-consegna-dichiarazione-di-conformita-impianti-cosa-succede),
    [Studio Madera — conformità impianti in affitto e vendita](https://www.studiomadera.it/news/326-conformita-affitto-vendita).
    """
    if fascicolo.tipo_transazione != "acquisto":
        return []
    if not fascicolo.atto_compravendita and not fascicolo.preliminare_compravendita:
        return []
    if not fascicolo.conformita_impianti:
        return [
            RedFlag(
                categoria="conformita_impianti",
                titolo="Dichiarazione di conformità degli impianti non presente nel fascicolo",
                gravita="bassa",
                descrizione=(
                    "Non risulta nessuna dichiarazione di conformità degli impianti (elettrico, "
                    "idraulico, gas, termico). Non incide sulla validità dell'atto — la compravendita "
                    "resta possibile anche senza — ma può rendere più difficile la trattativa, perché "
                    "acquirente e (in caso di successiva locazione) conduttore la richiedono come prova "
                    "di sicurezza. Se gli impianti sono anteriori al 13/03/1990, la dichiarazione "
                    "semplicemente non può essere pretesa (all'epoca non era ancora richiesta)."
                ),
                riferimento="D.M. 37/2008 (già L. 46/90)",
                azione_consigliata=(
                    "Verificare l'anno di installazione degli impianti: se successivo al 1990, provare "
                    "a recuperare la dichiarazione contattando la ditta installatrice originaria, "
                    "verificando presso lo Sportello Unico per l'Edilizia del Comune (dove la "
                    "documentazione va depositata entro 30 giorni dai lavori) o presso notaio/tecnico "
                    "che seguì l'intervento; se non recuperabile, valutare con un tecnico abilitato una "
                    "dichiarazione di rispondenza (DIRI) come alternativa, e in ogni caso menzionarne "
                    "l'assenza per iscritto all'acquirente."
                ),
            )
        ]
    non_conformi = [c for c in fascicolo.conformita_impianti if c.conforme is False]
    if not non_conformi:
        return []
    tipi = ", ".join(c.tipo_impianto or "impianto non specificato" for c in non_conformi)
    return [
        RedFlag(
            categoria="conformita_impianti",
            titolo="Impianto dichiarato non conforme",
            gravita="media",
            descrizione=(
                f"Risulta una dichiarazione di NON conformità per: {tipi}. La conformità degli "
                "impianti non è requisito di validità dell'atto, ma un impianto non conforme resta un "
                "rischio di sicurezza concreto e un costo da qualcuno sostenuto."
            ),
            riferimento="D.M. 37/2008 (già L. 46/90)",
            azione_consigliata=(
                "Chiarire per iscritto se la messa a norma è a carico del venditore prima del rogito "
                "oppure se l'acquirente accetta l'immobile assumendosene la responsabilità (con "
                "eventuale sconto commisurato al costo dell'intervento)."
            ),
        )
    ]


def check_ape_scaduto(fascicolo: Fascicolo, oggi: Optional[date] = None) -> list[RedFlag]:
    """L'APE ha validità di 10 anni dalla data di rilascio (salvo interventi
    che ne modifichino la prestazione energetica prima della scadenza). Un
    APE scaduto non può essere utilizzato per il rogito: va rinnovato prima
    di procedere, non solo "prima possibile" — a differenza di altri
    documenti mancanti, questo blocca concretamente la chiusura dell'atto.

    Controllo puramente deterministico (confronto date), quindi a costo
    zero: va eseguito sempre quando è presente un APE con data di scadenza.

    Fonte: certificato-ape.it — validità e obbligo di rinnovo prima del rogito.
    """
    ape = fascicolo.ape
    if not ape or not ape.data_scadenza:
        return []
    scadenza = _parse_data(ape.data_scadenza)
    if not scadenza:
        return []
    oggi = oggi or date.today()
    if scadenza >= oggi:
        return []
    return [
        RedFlag(
            categoria="ape",
            titolo="APE scaduto",
            gravita="alta",
            descrizione=(
                f"L'attestato di prestazione energetica risulta scaduto il {ape.data_scadenza} "
                "(validità 10 anni dal rilascio, salvo interventi che ne modifichino prima la "
                "prestazione energetica). Un APE scaduto non può essere utilizzato per il rogito: "
                "va commissionato un nuovo attestato prima di procedere, non solo aggiornato in un "
                "secondo momento."
            ),
            riferimento="D.Lgs. 192/2005 e s.m.i. sulla certificazione energetica; validità decennale dell'APE",
            azione_consigliata="Commissionare un nuovo APE prima di fissare la data del rogito, per evitare ritardi last-minute.",
        )
    ]


def check_ape_non_menzionato_in_atto(fascicolo: Fascicolo) -> list[RedFlag]:
    """La clausola sull'APE nell'atto di compravendita, non solo l'esistenza
    di un APE valido (quella la copre già `check_ape_scaduto`, su un
    documento diverso).

    Ogni atto di trasferimento immobiliare a titolo oneroso deve contenere
    gli estremi dell'attestato di prestazione energetica e la dichiarazione
    delle parti di averne preso visione: un obbligo di legge distinto
    dall'obbligo di avere un APE valido, con una conseguenza diversa. Fino
    al 23 dicembre 2013 la sanzione era la nullità dell'atto; il D.L.
    145/2013 (artt. 1, commi 7-8, in vigore dal 24 dicembre 2013) l'ha
    sostituita con una sanzione amministrativa pecuniaria da 3.000 a 18.000
    euro, in solido tra le parti — un cambio non banale, perché un atto che
    la ometta oggi resta valido ed efficace, solo esposto a una sanzione: un
    rischio economico concreto da prevenire prima del rogito, non un motivo
    per bloccare la vendita se scoperto dopo.

    Gravità "media": la sanzione è concreta e può essere rilevante (fino a
    18.000 euro), ma — a differenza di `check_locazione_non_registrata`, che
    riguarda una NULLITÀ tuttora vigente — qui la vendita resta comunque
    valida, quindi non ha lo stesso peso di un vizio che mette in discussione
    l'atto stesso.

    Fonti: [Notaio Arcoleo — l'attestato di prestazione
    energetica](https://www.notaioarcoleo.it/articoli-e-approfondimenti/diritti-reali/ape-lattestato-di-prestazione-energetica)
    (conferma il passaggio da nullità a sanzione amministrativa e ne riporta
    l'importo); [Directio — sanzione amministrativa per omessa dichiarazione
    del rilascio APE](https://www.directio.it/News/Details/1153) (conferma
    indipendente di importo e riferimento normativo esatto, incrociata prima
    di essere codificata).
    """
    if fascicolo.tipo_transazione != "acquisto":
        return []
    atto = fascicolo.atto_compravendita
    if not atto or atto.ape_menzionato_in_atto is not False:
        return []
    return [
        RedFlag(
            categoria="ape",
            titolo="Clausola sull'APE non presente nell'atto di compravendita",
            gravita="media",
            descrizione=(
                "Il testo dell'atto di compravendita non contiene (o non contiene più, se rivisto "
                "dopo l'estrazione) gli estremi dell'attestato di prestazione energetica né la "
                "dichiarazione delle parti di averne preso visione — un elemento obbligatorio per "
                "legge, distinto dalla semplice esistenza di un APE valido nel fascicolo. L'atto resta "
                "valido, ma espone le parti a una sanzione amministrativa pecuniaria in solido da 3.000 "
                "a 18.000 euro."
            ),
            riferimento="Art. 6, D.Lgs. 192/2005; D.L. 145/2013, art. 1, commi 7-8 (sanzione amministrativa in luogo della nullità dal 24/12/2013)",
            azione_consigliata=(
                "Verificare prima del rogito che il notaio inserisca in atto gli estremi dell'APE "
                "(classe energetica, numero identificativo) e la dichiarazione di presa visione delle "
                "parti — più semplice ed economico da prevenire in fase di redazione che da rimediare "
                "dopo la firma."
            ),
        )
    ]


# ---------------------------------------------------------------------------
# Condominio: regolamento e verbali
# ---------------------------------------------------------------------------

def check_vincoli_regolamento_condominio(fascicolo: Fascicolo) -> list[RedFlag]:
    reg = fascicolo.regolamento_condominio
    if not reg or not reg.limitazioni_uso:
        return []
    opponibile = (reg.tipo_regolamento or "").lower() == "contrattuale"
    return [
        RedFlag(
            categoria="condominio",
            titolo="Limitazioni d'uso nel regolamento condominiale",
            gravita="media" if opponibile else "bassa",
            descrizione=(
                f"Il regolamento condominiale ({reg.tipo_regolamento or 'tipo non specificato'}) "
                f"prevede le seguenti limitazioni: {', '.join(reg.limitazioni_uso)}. "
                + (
                    "Trattandosi di regolamento contrattuale, queste limitazioni sono opponibili a "
                    "tutti i proprietari, incluso il futuro acquirente."
                    if opponibile
                    else "Se il regolamento è assembleare/interno la sua opponibilità a un nuovo "
                    "proprietario è più limitata, ma va comunque verificata."
                )
            ),
            azione_consigliata="Verificare se le limitazioni sono compatibili con l'uso previsto dell'immobile (es. affitti brevi, uso commerciale).",
        )
    ]


def check_spese_straordinarie_ante_rogito(fascicolo: Fascicolo) -> list[RedFlag]:
    """Lavori straordinari deliberati PRIMA della data del rogito (o del
    preliminare, se l'atto non è ancora disponibile) ma non ancora eseguiti: di
    norma restano a carico di chi era proprietario al momento della delibera
    (il venditore), salvo diverso accordo esplicito nell'atto — un punto che va
    sempre chiarito per iscritto.
    """
    data_riferimento = None
    if fascicolo.atto_compravendita:
        data_riferimento = _parse_data(fascicolo.atto_compravendita.data_atto)
    elif fascicolo.preliminare_compravendita:
        data_riferimento = _parse_data(fascicolo.preliminare_compravendita.data)

    flags = []
    for verbale in fascicolo.verbali_assemblea:
        for delibera in verbale.delibere:
            if delibera.lavori_gia_eseguiti:
                continue
            data_delibera = _parse_data(delibera.data_delibera)
            if data_riferimento and data_delibera and data_delibera >= data_riferimento:
                continue  # delibera successiva al rogito: normale competenza dell'acquirente
            flags.append(
                RedFlag(
                    categoria="condominio",
                    titolo="Spesa straordinaria deliberata non ancora eseguita",
                    gravita="media",
                    descrizione=(
                        f"Delibera del {delibera.data_delibera or 'data non specificata'} per "
                        f"'{delibera.oggetto or 'lavori non specificati'}'"
                        + (f" (importo totale {delibera.importo_totale_eur:.0f} EUR)" if delibera.importo_totale_eur else "")
                        + ", lavori non ancora eseguiti. Di norma le spese deliberate prima del rogito "
                        "restano a carico di chi era proprietario al momento della delibera (il "
                        "venditore), indipendentemente da quando i lavori vengono eseguiti o fatturati "
                        "— ma è sempre buona norma chiarirlo esplicitamente nell'atto."
                    ),
                    riferimento="Art. 63, comma 5, disp. att. c.c. e prassi giurisprudenziale sul riparto delibera/rogito",
                    azione_consigliata="Chiarire esplicitamente in atto chi si accolla questa spesa, anche se la regola generale la pone a carico del venditore.",
                )
            )
    return flags


def check_morosita_condominiale(fascicolo: Fascicolo) -> list[RedFlag]:
    if any(v.morosita_menzionata for v in fascicolo.verbali_assemblea):
        return [
            RedFlag(
                categoria="condominio",
                titolo="Morosità condominiale menzionata nei verbali",
                gravita="bassa",
                descrizione=(
                    "Uno o più verbali di assemblea menzionano condomini morosi o azioni di recupero "
                    "crediti. Non riguarda necessariamente l'unità in vendita, ma un condominio con "
                    "morosità diffusa può indicare rischio di spese impreviste o di gestione difficoltosa."
                ),
                azione_consigliata="Chiedere l'attestazione dello stato dei pagamenti (art. 63 disp. att. c.c.) relativa specificamente all'unità in vendita.",
            )
        ]
    return []


# ---------------------------------------------------------------------------
# Contratto di locazione: registrazione obbligatoria e prelazione del
# conduttore commerciale in caso di vendita
# ---------------------------------------------------------------------------

def check_locazione_non_registrata(fascicolo: Fascicolo) -> list[RedFlag]:
    """La registrazione del contratto di locazione di immobili entro 30
    giorni dalla stipula non è solo un adempimento fiscale: dal 2004 la sua
    omissione rende il contratto NULLO (art. 1, comma 346, L. 311/2004), oltre
    a esporre le parti a sanzioni amministrative (120%-240% dell'imposta di
    registro dovuta, più penalità aggiuntive se il canone dichiarato è
    inferiore al reale).

    Nota: questo controllo scatta SOLO se `registrato` è esplicitamente
    False (dichiarato nel documento o in un allegato) — l'assenza di
    menzione nel testo del contratto NON implica automaticamente la mancata
    registrazione (che è un fatto successivo alla firma, di norma non
    attestato dal contratto stesso). Vedi il docstring del campo in
    schemas.ContrattoLocazione.

    Fonte: fiscoetasse.com — conseguenze del contratto di locazione non registrato.
    """
    contratto = fascicolo.contratto_locazione
    if not contratto or contratto.registrato is not False:
        return []
    return [
        RedFlag(
            categoria="locazione",
            titolo="Contratto di locazione non registrato",
            gravita="alta",
            descrizione=(
                "Il contratto di locazione risulta non registrato. Dal 2004 la mancata registrazione "
                "entro 30 giorni dalla stipula rende il contratto NULLO (non solo irregolare "
                "fiscalmente), oltre a esporre le parti a sanzioni amministrative significative "
                "(120%-240% dell'imposta di registro dovuta)."
            ),
            riferimento="Art. 1, comma 346, L. 311/2004 (nullità per omessa registrazione)",
            azione_consigliata="Procedere alla registrazione presso l'Agenzia delle Entrate prima di considerare il contratto valido a tutti gli effetti; verificare se sono nel frattempo maturate sanzioni.",
        )
    ]


def check_prelazione_conduttore_commerciale(fascicolo: Fascicolo) -> list[RedFlag]:
    """Se l'immobile in vendita è locato per uso NON abitativo (commerciale,
    ufficio, artigianale...), il conduttore ha diritto di prelazione
    sull'acquisto ex art. 38-39 L. 392/1978: il locatore/venditore deve
    notificargli tramite ufficiale giudiziario prezzo e condizioni della
    vendita PRIMA di concludere il contratto con un terzo, e il conduttore ha
    60 giorni per accettare offrendo le stesse condizioni.

    Se questo adempimento viene saltato (o il prezzo dichiarato al conduttore
    è più alto di quello reale), il conduttore può esercitare il diritto di
    RISCATTO (retratto) entro 6 mesi dalla registrazione del contratto di
    vendita, facendosi retrocedere l'immobile al posto dell'acquirente — un
    rischio che può travolgere una vendita già conclusa e rogitata, non solo
    una trattativa in corso. Eccezioni principali: vendita a coniuge o
    parenti entro il secondo grado, trasferimenti per successione, vendite
    non onerose (donazioni), vendite forzate/fallimentari.

    Per un agente immobiliare questo è uno dei rischi procedurali più gravi
    dell'intera vendita di un immobile commerciale locato, perché si
    materializza DOPO il rogito: per questo la gravità resta "alta" anche in
    assenza di altri segnali di criticità nel fascicolo.

    Confronta i riferimenti catastali del contratto di locazione con quelli
    dell'atto/preliminare (riusando consistency._riferimenti_coincidono) per
    evitare falsi positivi quando la locazione riguarda un'unità DIVERSA da
    quella in vendita nello stesso fascicolo (es. un altro subalterno dello
    stesso edificio). Se mancano riferimenti sufficienti per escludere che
    sia la stessa unità, il controllo scatta comunque per precauzione — dato
    l'impatto potenziale (riscatto post-rogito), è più sicuro un falso
    positivo da verificare che un falso negativo.

    Fonti: brocardi.it (testo e commento art. 38 L. 392/1978), studiolegaleluciano.it
    (disciplina della prelazione commerciale).
    """
    contratto = fascicolo.contratto_locazione
    if not contratto or not contratto.uso:
        return []
    uso_lower = contratto.uso.lower()
    # Attenzione: un controllo ingenuo tipo "'abitativ' in uso_lower" avrebbe
    # un falso negativo qui, perché la stringa "abitativ" è una substring
    # anche di "NON abitativo" — matchiamo quindi positivamente sugli
    # indicatori di uso non abitativo invece di escludere sulla negazione.
    indicatori_non_abitativo = (
        "commercial", "ufficio", "non abitativ", "diverso da abitazion",
        "artigianal", "negozio", "studio profession",
    )
    if not any(ind in uso_lower for ind in indicatori_non_abitativo):
        return []
    atto_o_prel = fascicolo.atto_compravendita or fascicolo.preliminare_compravendita
    if not atto_o_prel:
        return []
    rif_vendita = atto_o_prel.riferimenti_catastali
    rif_locazione = contratto.riferimenti_catastali
    if rif_vendita and rif_locazione:
        stessa_unita = any(_riferimenti_coincidono(a, b) for a in rif_vendita for b in rif_locazione)
        if not stessa_unita:
            return []  # riferimenti presenti su entrambi i lati e chiaramente diversi: non è la stessa unità
    return [
        RedFlag(
            categoria="locazione",
            titolo="Prelazione del conduttore commerciale sulla vendita",
            gravita="alta",
            descrizione=(
                f"L'immobile è locato per uso non abitativo ({contratto.uso}): il conduttore ha "
                "diritto di prelazione sulla vendita ex art. 38 L. 392/1978, salvo eccezioni (vendita "
                "a coniuge/parenti entro il secondo grado, successione, donazione, vendita forzata). "
                "Il venditore deve avergli notificato tramite ufficiale giudiziario prezzo e "
                "condizioni PRIMA di vendere a terzi, con 60 giorni per accettare. Se questo passaggio "
                "non risulta effettuato, il conduttore può esercitare il RISCATTO entro 6 mesi dalla "
                "registrazione della vendita, anche a rogito già avvenuto."
            ),
            riferimento="Art. 38-39 L. 392/1978 (prelazione e riscatto del conduttore commerciale)",
            azione_consigliata=(
                "Verificare con il venditore se la denuntiatio è già stata notificata al conduttore e, "
                "in caso negativo, farla effettuare tramite ufficiale giudiziario prima del rogito — o "
                "verificare che ricorra una delle eccezioni di legge."
            ),
        )
    ]


# ---------------------------------------------------------------------------
# Relazione tecnica integrata (geometra/tecnico) e obbligo di verifica/
# informazione dell'AGENTE IMMOBILIARE
#
# Questo blocco è pensato esplicitamente per chi usa lo strumento come
# supporto al proprio lavoro di agente immobiliare (mediatore ex L. 39/1989),
# non solo per l'acquirente finale: l'agente ha un obbligo di legge — non
# solo una buona pratica — di verificare la conformità urbanistica/catastale
# o, se non lo fa, di dichiararlo esplicitamente al cliente.
# ---------------------------------------------------------------------------

def check_difformita_da_relazione_tecnica(fascicolo: Fascicolo) -> list[RedFlag]:
    """Se una relazione tecnica integrata (redatta da un geometra/tecnico
    abilitato) è presente nel fascicolo e segnala difformità di conformità
    catastale/urbanistica, questa è un'evidenza tecnica diretta — più forte di
    una semplice assenza di documentazione — e va trattata con gravità più
    alta di un semplice "manca il titolo edilizio".

    Le difformità che il tecnico stesso dichiara rientrare nelle tolleranze
    costruttive (art. 34-bis DPR 380/2001, es. lievi scostamenti dimensionali)
    non richiedono sanatoria e sono quindi declassate a gravità inferiore.

    Fonti: notaiofacile.it (relazione tecnica integrata), biblus.acca.it
    (stato legittimo e tolleranze art. 34-bis DPR 380/2001).
    """
    rti = fascicolo.relazione_tecnica_integrata
    if not rti:
        return []
    flags = []
    problemi = []
    if rti.conformita_catastale is False:
        problemi.append("non conforme catastalmente")
    if rti.conformita_urbanistica is False:
        problemi.append("non conforme urbanisticamente")
    if rti.difformita_riscontrate:
        problemi.append(f"difformità riscontrate: {', '.join(rti.difformita_riscontrate)}")

    if not problemi:
        return []

    entro_tolleranza = rti.difformita_rientrano_in_tolleranza is True
    gravita = "media" if entro_tolleranza else "alta"
    flags.append(
        RedFlag(
            categoria="conformita_tecnica",
            titolo="Difformità rilevate dalla relazione tecnica integrata",
            gravita=gravita,
            descrizione=(
                f"La relazione tecnica redatta da {rti.tecnico_redattore or 'un tecnico abilitato'} "
                f"({rti.tipo_tecnico or 'tipo non specificato'}) segnala: {'; '.join(problemi)}. "
                + (
                    "Il tecnico dichiara che le difformità rientrano nelle tolleranze costruttive "
                    "(art. 34-bis DPR 380/2001) e non richiedono sanatoria, ma vanno comunque "
                    "menzionate all'acquirente."
                    if entro_tolleranza
                    else "Non risulta che le difformità rientrino nelle tolleranze costruttive: "
                    "potrebbero richiedere una sanatoria prima del rogito o incidere sul valore/"
                    "commerciabilità dell'immobile."
                )
            ),
            riferimento="Art. 34-bis DPR 380/2001 (tolleranze costruttive); Testo Unico Edilizia",
            azione_consigliata=(
                "Verificare con il tecnico se è necessaria una sanatoria e, in caso affermativo, "
                "chi se ne fa carico e con quali tempi prima del rogito. Le soluzioni di prassi, se "
                "la difformità è sanabile, sono: (1) sanatoria prima del rogito — la più pulita, ma "
                "richiede tempo e un esborso (oneri concessori indicativamente 333-516 € per lavori "
                "non ultimati, fino a circa 1.000 € se già eseguiti, più 500-1.000 € di parcella "
                "tecnica: cifre indicative, da verificare con il tecnico incaricato); (2) vendita con "
                "difformità dichiarata in preliminare e responsabilità/tempistica della sanatoria "
                "attribuita per iscritto (di norma al venditore, ma negoziabile) — in alternativa alla "
                "sanatoria, una riduzione di prezzo concordata è prassi comune: in un caso concreto "
                "documentato (mbg.legal, un manufatto abusivo che violava le distanze minime dai "
                "confini) l'acquirente ha negoziato uno sconto di 25.000 € commisurato ai costi di "
                "ripristino/demolizione invece di richiedere la sanatoria, dando un ordine di "
                "grandezza di quanto possa incidere una difformità non sanabile sulla trattativa; "
                "(3) se la sanatoria "
                "è già stata richiesta ma non ancora evasa, procedere solo dopo aver verificato con "
                "il tecnico se e come vanno menzionati in atto gli estremi della domanda (art. 40, "
                "comma 2, L. 47/1985: la menzione mancante o inesatta rende l'atto nullo — vedi anche "
                "text_rules.py, regola 'condono_edilizio', se un condono è menzionato nel testo "
                "indicizzato). Se la difformità NON è sanabile, la vendita nello stato di fatto è comunque possibile solo "
                "con piena disclosure scritta all'acquirente: mai procedere presentandola come "
                "questione minore."
            ),
        )
    )
    return flags


def check_relazione_tecnica_assente(fascicolo: Fascicolo) -> list[RedFlag]:
    """L'agente immobiliare NON può limitarsi a riportare le dichiarazioni del
    venditore sulla conformità urbanistica/catastale: secondo Cass.
    24534/2022, in forza dell'obbligo di informazione ex art. 1759 c.c. e
    della diligenza professionale ex art. 1176, comma 2, c.c., deve verificare
    (tipicamente incaricando un tecnico per una relazione tecnica integrata) o
    dichiarare esplicitamente al cliente di non averlo fatto.

    Questo controllo non segnala un problema dell'immobile in sé, ma un
    adempimento mancante dell'agente: per questo la gravità resta "media" (va
    comunque gestito prima di procedere) anche quando nessun'altra criticità
    urbanistica è emersa altrove nel fascicolo.

    Il dovere di verifica NON è però illimitato, e due sentenze più recenti
    chiariscono i confini, evitando di far percepire questo controllo come
    una responsabilità assoluta dell'agente:
    - Cass. 32264/2025: la diligenza dell'agente si valuta al MOMENTO della
      conclusione dell'affare, con i documenti che aveva a disposizione
      allora — una difformità emersa (o un titolo edilizio ottenuto) SOLO
      dopo non genera responsabilità retroattiva.
    - Cass. 14158/2019: l'agente non è tenuto a verifiche di natura
      squisitamente tecnica (es. agibilità) che esulano dalla sua
      competenza professionale, salvo che le abbia occultate pur
      conoscendole, le abbia rappresentate falsamente, o si sia impegnato
      espressamente a eseguirle.
    In pratica: questo controllo segnala l'ASSENZA di una verifica tecnica
    nel fascicolo raccolto FINORA (un gap da colmare prima del rogito), non
    un giudizio di responsabilità già maturata — che dipende da cosa
    l'agente sapeva/poteva sapere nel momento in cui ha operato.

    Fonti: studiotecnicopagliai.it su Cass. 24534/2022 e obblighi del
    mediatore immobiliare; art. 1759 c.c.; art. 1176 c.c.; L. 39/1989;
    studiolegalecalvello.it su Cass. 32264/2025; studiotecnicopagliai.it su
    Cass. 14158/2019 (esclusione di responsabilità per verifiche tecniche
    fuori competenza).
    """
    if fascicolo.tipo_transazione != "acquisto":
        return []
    if not fascicolo.atto_compravendita and not fascicolo.preliminare_compravendita:
        return []
    if fascicolo.relazione_tecnica_integrata:
        return []
    return [
        RedFlag(
            categoria="obblighi_mediatore",
            titolo="Nessuna verifica tecnica di conformità agli atti: da dichiarare al cliente",
            gravita="media",
            descrizione=(
                "Non risulta nel fascicolo una relazione tecnica integrata (o altro accertamento "
                "tecnico) sulla conformità catastale/urbanistica. Secondo Cass. 24534/2022, il "
                "mediatore immobiliare non può limitarsi alle dichiarazioni del venditore su questi "
                "aspetti: deve verificare con la diligenza del professionista medio (art. 1176, comma "
                "2, c.c.) oppure dichiarare esplicitamente al cliente di non aver effettuato la "
                "verifica, in adempimento dell'obbligo di informazione ex art. 1759 c.c."
            ),
            riferimento="Art. 1759 c.c.; art. 1176, comma 2, c.c.; L. 39/1989; Cass. 24534/2022",
            azione_consigliata=(
                "Incaricare un tecnico abilitato (geometra, architetto, ingegnere) di una relazione "
                "tecnica integrata, oppure mettere per iscritto al cliente che la conformità non è "
                "stata verificata e si basa solo sulle dichiarazioni del venditore."
            ),
        )
    ]


# ---------------------------------------------------------------------------
# Perizia di stima vs. prezzo pattuito
# ---------------------------------------------------------------------------

def check_perizia_sotto_prezzo(
    fascicolo: Fascicolo,
    margine_media: float = 0.05,
    margine_alta: float = 0.15,
) -> list[RedFlag]:
    """Confronta il valore stimato dalla/e perizia/e di stima con il prezzo
    pattuito (atto o, in mancanza, preliminare). La banca eroga il mutuo sulla
    base del MINORE tra valore periziato e prezzo di acquisto (loan-to-value
    tipicamente fino all'80% di quel valore): una perizia sotto prezzo riduce
    il mutuo erogabile, costringendo l'acquirente a coprire la differenza con
    capitale proprio o a rinegoziare — un rischio concreto di far saltare una
    trattativa già chiusa dall'agente.

    Le soglie (5%/15%) sono indicative: un piccolo scarto è normale (le
    perizie non coincidono mai esattamente col prezzo di mercato), quindi
    flaggiamo solo scarti che iniziano a essere rilevanti per la sostenibilità
    del mutuo.

    Fonti: mutui.it e idealista.it su perizia immobiliare e loan-to-value.
    """
    prezzo_doc = fascicolo.atto_compravendita or fascicolo.preliminare_compravendita
    if not prezzo_doc or not prezzo_doc.prezzo_eur or not prezzo_doc.prezzo_eur.valore:
        return []
    try:
        prezzo = float(str(prezzo_doc.prezzo_eur.valore).replace(",", "."))
    except ValueError:
        return []
    if prezzo <= 0:
        return []

    flags = []
    for perizia in fascicolo.perizie_di_stima:
        if not perizia.valore_stimato_eur or not perizia.valore_stimato_eur.valore:
            continue
        try:
            valore_perizia = float(str(perizia.valore_stimato_eur.valore).replace(",", "."))
        except ValueError:
            continue
        if valore_perizia <= 0:
            continue
        scarto = (prezzo - valore_perizia) / prezzo
        if scarto <= margine_media:
            continue
        gravita = "alta" if scarto > margine_alta else "media"
        flags.append(
            RedFlag(
                categoria="perizia_valore",
                titolo="Perizia di stima inferiore al prezzo pattuito",
                gravita=gravita,
                descrizione=(
                    f"La perizia di {perizia.perito or 'un perito'} ({perizia.finalita or 'finalità non specificata'}) "
                    f"stima l'immobile {scarto:.0%} sotto il prezzo pattuito di {prezzo:,.0f} EUR. "
                    "La banca eroga il mutuo sulla base del valore MINORE tra perizia e prezzo "
                    "(loan-to-value tipicamente fino all'80% di quel valore): uno scarto di questa "
                    "entità può ridurre l'importo mutuabile e costringere l'acquirente a coprire la "
                    "differenza con capitale proprio, con rischio concreto per la tenuta della trattativa."
                ),
                riferimento="Prassi bancaria su loan-to-value nei mutui ipotecari",
                azione_consigliata=(
                    "Verificare con l'acquirente la disponibilità di capitale proprio aggiuntivo, o "
                    "valutare con il venditore un adeguamento del prezzo prima di procedere oltre."
                ),
            )
        )
    return flags


# ---------------------------------------------------------------------------
# Vincoli su CDU
# ---------------------------------------------------------------------------

_PAROLE_CHIAVE_VINCOLO_STORICO = ("storic", "artistic", "cultural", "bene culturale", "belle arti", "soprintendenza")


def _e_vincolo_storico_artistico(vincolo: str) -> bool:
    v = vincolo.lower()
    return any(parola in v for parola in _PAROLE_CHIAVE_VINCOLO_STORICO)


def check_vincoli_cdu(fascicolo: Fascicolo) -> list[RedFlag]:
    """Vincoli "generici" (paesaggistico, idrogeologico, sismico,
    archeologico) che limitano interventi futuri ma non comportano di per sé
    un adempimento procedurale specifico per la vendita in corso. I vincoli
    storico-artistico-culturali sono volutamente ESCLUSI da qui (li tratta
    check_vincolo_storico_artistico a gravità più alta, perché comportano un
    obbligo di denuncia con conseguenze concrete sulla vendita)."""
    if not fascicolo.cdu or not fascicolo.cdu.vincoli:
        return []
    vincoli_generici = [v for v in fascicolo.cdu.vincoli if not _e_vincolo_storico_artistico(v)]
    if not vincoli_generici:
        return []
    return [
        RedFlag(
            categoria="vincoli",
            titolo="Vincoli urbanistici/paesaggistici sull'area",
            gravita="bassa",
            descrizione=(
                f"Il certificato di destinazione urbanistica riporta i seguenti vincoli: "
                f"{', '.join(vincoli_generici)}. Non impediscono di per sé la vendita, ma possono "
                "limitare interventi edilizi futuri (ampliamenti, cambi di destinazione)."
            ),
            azione_consigliata="Se sono previsti interventi futuri, verificare con un tecnico la compatibilità con i vincoli indicati.",
        )
    ]


def check_vincolo_storico_artistico(fascicolo: Fascicolo) -> list[RedFlag]:
    """Un vincolo storico-artistico-culturale (D.Lgs. 42/2004, "Codice dei
    beni culturali e del paesaggio", parte seconda) è sostanzialmente diverso
    da un vincolo paesaggistico "semplice": comporta un obbligo di DENUNCIA
    della vendita alla Soprintendenza entro 30 giorni dall'atto, durante il
    quale lo Stato (o Regione/Comune) ha 60 giorni di tempo per esercitare la
    PRELAZIONE all'acquisto alle stesse condizioni pattuite (il contratto tra
    le parti resta valido ma sospeso in attesa che il termine scada). Se la
    denuncia viene omessa, l'atto è inefficace nei confronti dello Stato
    (che può comunque esercitare la prelazione anche dopo), il termine per
    l'eventuale prelazione tardiva sale a 180 giorni, e sono previste sanzioni
    penali per l'omessa denuncia (art. 173 D.Lgs. 42/2004).

    Fonte: notaiotassitani.it — compravendita di immobili con vincolo
    storico-artistico-culturale; brocardi.it — art. 60 Codice dei beni
    culturali (acquisto in via di prelazione).
    """
    if not fascicolo.cdu or not fascicolo.cdu.vincoli:
        return []
    vincoli_storici = [v for v in fascicolo.cdu.vincoli if _e_vincolo_storico_artistico(v)]
    if not vincoli_storici:
        return []
    return [
        RedFlag(
            categoria="vincoli",
            titolo="Vincolo storico-artistico-culturale: obbligo di denuncia e prelazione dello Stato",
            gravita="alta",
            descrizione=(
                f"Il certificato di destinazione urbanistica segnala un vincolo di natura "
                f"storico-artistico-culturale: {', '.join(vincoli_storici)}. A differenza di un "
                "vincolo puramente paesaggistico, questo comporta l'obbligo di denunciare la vendita "
                "alla Soprintendenza entro 30 giorni dall'atto: lo Stato ha 60 giorni per esercitare la "
                "prelazione alle stesse condizioni pattuite (il contratto resta valido ma sospeso nel "
                "frattempo). Se la denuncia viene omessa, l'atto è inefficace verso lo Stato (che può "
                "esercitare la prelazione comunque, con termine esteso a 180 giorni) e sono previste "
                "sanzioni penali per l'omessa denuncia."
            ),
            riferimento="Artt. 59-62 e 173 D.Lgs. 42/2004 (Codice dei beni culturali e del paesaggio)",
            azione_consigliata="Verificare con un notaio la corretta predisposizione della denuncia di alienazione da presentare alla Soprintendenza entro 30 giorni dall'atto; non dare per scontato che equivalga a un vincolo paesaggistico ordinario.",
        )
    ]


# ---------------------------------------------------------------------------
# Coerenza preliminare / atto definitivo
# ---------------------------------------------------------------------------

def check_preliminare_vs_atto(fascicolo: Fascicolo) -> list[RedFlag]:
    prel = fascicolo.preliminare_compravendita
    atto = fascicolo.atto_compravendita
    if not prel or not atto:
        return []
    flags = []
    if prel.prezzo_eur and prel.prezzo_eur.valore and atto.prezzo_eur and atto.prezzo_eur.valore:
        # Stessa logica di parsing usata altrove nel codebase (consistency.py,
        # check_perizia_sotto_prezzo qui sotto): solo `.replace(",", ".")`,
        # assumendo la virgola come separatore decimale e nessun separatore
        # delle migliaia. In precedenza il ramo `p_prel` faceva in più
        # `.replace(".", "", 1)` per gestire un formato italiano con punto
        # delle migliaia (es. "285.000,00") — ma applicato a un valore già
        # nel formato semplice "290000.00" (un punto come separatore
        # decimale, plausibile output dell'estrattore) eliminava il punto
        # decimale stesso, moltiplicando il prezzo per 100 e generando un
        # falso positivo "prezzo diverso" anche quando preliminare e atto
        # riportavano lo STESSO importo. Vedi tests/test_red_flags.py per il
        # caso di regressione.
        try:
            p_prel = float(str(prel.prezzo_eur.valore).replace(",", "."))
        except ValueError:
            p_prel = None
        try:
            p_atto = float(str(atto.prezzo_eur.valore).replace(",", "."))
        except ValueError:
            p_atto = None
        if p_prel is not None and p_atto is not None and abs(p_prel - p_atto) > 0.01 * max(p_prel, p_atto, 1):
            flags.append(
                RedFlag(
                    categoria="coerenza_documentale",
                    titolo="Prezzo diverso tra preliminare e atto definitivo",
                    gravita="media",
                    descrizione=(
                        f"Il preliminare indica un prezzo di {prel.prezzo_eur.valore} mentre l'atto "
                        f"definitivo indica {atto.prezzo_eur.valore}. Un disallineamento può avere "
                        "spiegazioni legittime (rinegoziazione, oneri accessori) ma va sempre chiarito: "
                        "in alcuni casi uno scarto ingiustificato tra i due importi è stato usato per "
                        "occultare pagamenti in nero, con implicazioni fiscali per entrambe le parti."
                    ),
                    azione_consigliata="Chiedere spiegazione scritta del disallineamento prima del rogito.",
                )
            )
    return flags


# ---------------------------------------------------------------------------
# Esecuzione di tutti i controlli
# ---------------------------------------------------------------------------

_ALL_CHECKS = [
    check_provenienza_donativa,
    check_successione_non_divisa,
    check_diritto_abitazione_coniuge_superstite,
    check_comunione_legale_coniuge_non_intervenuto,
    check_decadenza_prima_casa_venditore,
    check_formalita_pregiudizievoli,
    check_conformita_catastale_mancante,
    check_titolo_edilizio_mancante,
    check_agibilita_mancante,
    check_conformita_impianti_assente,
    check_ape_scaduto,
    check_ape_non_menzionato_in_atto,
    check_vincoli_regolamento_condominio,
    check_spese_straordinarie_ante_rogito,
    check_morosita_condominiale,
    check_locazione_non_registrata,
    check_prelazione_conduttore_commerciale,
    check_difformita_da_relazione_tecnica,
    check_relazione_tecnica_assente,
    check_perizia_sotto_prezzo,
    check_vincoli_cdu,
    check_vincolo_storico_artistico,
    check_preliminare_vs_atto,
]


def run_all_red_flags(fascicolo: Fascicolo) -> list[RedFlag]:
    flags: list[RedFlag] = []
    for check in _ALL_CHECKS:
        flags.extend(check(fascicolo))
    ordine_gravita = {"critica": 0, "alta": 1, "media": 2, "bassa": 3}
    flags.sort(key=lambda f: ordine_gravita.get(f.gravita, 9))
    return flags


