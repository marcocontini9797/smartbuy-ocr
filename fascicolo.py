"""
Fascicolo: il contenitore che raccoglie TUTTI i documenti (estratti e verificati)
relativi a una singola pratica immobiliare, di qualunque tipo tra quelli
supportati. È l'unità su cui lavorano red_flags.py (controlli deterministici)
e due_diligence.py (report finale, deterministico + LLM).

Un fascicolo può avere zero o un documento per i tipi "singoli" (un solo atto
di compravendita, una sola APE...) e più documenti per i tipi che naturalmente
si ripetono (più visure ipotecarie, più titoli edilizi nel tempo, più verbali
di assemblea).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel
from observability import new_id, stable_id

from consistency import MissingInfoReport, generate_missing_info_questions
from schemas import (
    APE,
    AttoCompravendita,
    AttoDiProvenienza,
    CertificatoAgibilita,
    CertificatoDestinazioneUrbanistica,
    CertificatoPrevenzioneIncendi,
    ContrattoLocazione,
    DichiarazioneConformitaImpianti,
    LicenzaCommerciale,
    PeriziaDiStima,
    Planimetria,
    PreliminareCompravendita,
    RegolamentoCondominio,
    RelazioneTecnicaIntegrata,
    TipoDocumento,
    TitoloEdilizio,
    VerbaleAssembleaCondominio,
    VisuraCamerale,
    VisuraCatastale,
    VisuraIpotecaria,
)


@dataclass
class Fascicolo:
    tipo_transazione: str = "acquisto"  # "acquisto" | "affitto"

    atto_compravendita: Optional[AttoCompravendita] = None
    preliminare_compravendita: Optional[PreliminareCompravendita] = None
    visura_catastale: Optional[VisuraCatastale] = None
    ape: Optional[APE] = None
    planimetria: Optional[Planimetria] = None
    contratto_locazione: Optional[ContrattoLocazione] = None
    cdu: Optional[CertificatoDestinazioneUrbanistica] = None
    agibilita: Optional[CertificatoAgibilita] = None
    regolamento_condominio: Optional[RegolamentoCondominio] = None
    atto_provenienza: Optional[AttoDiProvenienza] = None
    relazione_tecnica_integrata: Optional[RelazioneTecnicaIntegrata] = None
    licenza_commerciale: Optional[LicenzaCommerciale] = None
    certificato_prevenzione_incendi: Optional[CertificatoPrevenzioneIncendi] = None
    visura_camerale: Optional[VisuraCamerale] = None

    visure_ipotecarie: list[VisuraIpotecaria] = field(default_factory=list)
    perizie_di_stima: list[PeriziaDiStima] = field(default_factory=list)
    titoli_edilizi: list[TitoloEdilizio] = field(default_factory=list)
    verbali_assemblea: list[VerbaleAssembleaCondominio] = field(default_factory=list)
    conformita_impianti: list[DichiarazioneConformitaImpianti] = field(default_factory=list)

    # Documenti di tipo non riconosciuto o senza schema dedicato: teniamo
    # comunque traccia che esistono nel fascicolo (utile per il report finale
    # e per il retrieval RAG, anche se non entrano nei controlli deterministici).
    altri_documenti: list[str] = field(default_factory=list)

    property_id: str = field(default_factory=new_id, kw_only=True)
    # Canonical IDs keyed by stable slot, not by extracted values or document type alone.
    document_ids: dict[str, str] = field(default_factory=dict, kw_only=True)

    def document_id_for(self, doc: BaseModel) -> str:
        for name, value in vars(self).items():
            if value is doc:
                return self.document_ids.setdefault(name, stable_id("local-document", self.property_id, name))
            if isinstance(value, list):
                for index, item in enumerate(value):
                    if item is doc:
                        key = f"{name}/{index}"
                        return self.document_ids.setdefault(key, stable_id("local-document", self.property_id, key))
        raise ValueError("Document is not in this case")

    def tutti_i_documenti(self) -> list[BaseModel]:
        """Ritorna tutti i documenti Pydantic presenti nel fascicolo, in una lista piatta."""
        singoli = [
            self.atto_compravendita,
            self.preliminare_compravendita,
            self.visura_catastale,
            self.ape,
            self.planimetria,
            self.contratto_locazione,
            self.cdu,
            self.agibilita,
            self.regolamento_condominio,
            self.atto_provenienza,
            self.relazione_tecnica_integrata,
            self.licenza_commerciale,
            self.certificato_prevenzione_incendi,
            self.visura_camerale,
        ]
        multipli = (
            self.visure_ipotecarie
            + self.titoli_edilizi
            + self.verbali_assemblea
            + self.conformita_impianti
            + self.perizie_di_stima
        )
        return [d for d in singoli if d is not None] + multipli


# Campi del Fascicolo su cui aggiungere un documento del tipo corrispondente.
_SINGOLO_FIELD_BY_TIPO = {
    TipoDocumento.ATTO_COMPRAVENDITA: "atto_compravendita",
    TipoDocumento.PRELIMINARE_COMPRAVENDITA: "preliminare_compravendita",
    TipoDocumento.VISURA_CATASTALE: "visura_catastale",
    TipoDocumento.APE: "ape",
    TipoDocumento.PLANIMETRIA: "planimetria",
    TipoDocumento.CONTRATTO_LOCAZIONE: "contratto_locazione",
    TipoDocumento.CERTIFICATO_DESTINAZIONE_URBANISTICA: "cdu",
    TipoDocumento.CERTIFICATO_AGIBILITA: "agibilita",
    TipoDocumento.REGOLAMENTO_CONDOMINIO: "regolamento_condominio",
    TipoDocumento.ATTO_DI_PROVENIENZA: "atto_provenienza",
    TipoDocumento.RELAZIONE_TECNICA_INTEGRATA: "relazione_tecnica_integrata",
    TipoDocumento.LICENZA_COMMERCIALE: "licenza_commerciale",
    TipoDocumento.CERTIFICATO_PREVENZIONE_INCENDI: "certificato_prevenzione_incendi",
    TipoDocumento.VISURA_CAMERALE: "visura_camerale",
}
_MULTIPLO_FIELD_BY_TIPO = {
    TipoDocumento.VISURA_IPOTECARIA: "visure_ipotecarie",
    TipoDocumento.TITOLO_EDILIZIO: "titoli_edilizi",
    TipoDocumento.VERBALE_ASSEMBLEA_CONDOMINIO: "verbali_assemblea",
    TipoDocumento.DICHIARAZIONE_CONFORMITA_IMPIANTI: "conformita_impianti",
    TipoDocumento.PERIZIA_DI_STIMA: "perizie_di_stima",
}


def aggiungi_al_fascicolo(fascicolo: Fascicolo, tipo: TipoDocumento, documento: BaseModel, *, document_id: str | None = None) -> None:
    """Inserisce un documento estratto nel campo giusto del fascicolo, in base al tipo."""
    if document_id is not None and document_id in fascicolo.document_ids.values():
        raise ValueError("Canonical document already attached")
    if tipo in _SINGOLO_FIELD_BY_TIPO:
        slot = _SINGOLO_FIELD_BY_TIPO[tipo]
        setattr(fascicolo, slot, documento)
        fascicolo.document_ids[slot] = document_id or fascicolo.document_ids.get(slot) or new_id()
    elif tipo in _MULTIPLO_FIELD_BY_TIPO:
        slot = _MULTIPLO_FIELD_BY_TIPO[tipo]
        items = getattr(fascicolo, slot)
        fascicolo.document_ids[f"{slot}/{len(items)}"] = document_id or new_id()
        items.append(documento)
    else:
        fascicolo.altri_documenti.append(tipo.value)


# ---------------------------------------------------------------------------
# Checklist dei documenti attesi per tipo di transazione.
#
# Fonti: checklist "documenti che l'agente immobiliare deve reperire prima di
# acquisire/vendere un immobile" (join-iad.it e le altre fonti tecniche/
# notarili citate nel README), integrate con la prassi corrente di due
# diligence immobiliare. La relazione tecnica integrata non è un obbligo di
# legge, ma è inclusa qui perché è lo strumento concreto con cui l'AGENTE
# adempie al proprio obbligo di verifica/informazione ex art. 1759 c.c. (Cass.
# 24534/2022, vedi README): senza di essa l'agente deve comunque dichiarare
# esplicitamente al cliente di non aver verificato la conformità — non può
# limitarsi a riportare le dichiarazioni del venditore.
# ---------------------------------------------------------------------------

DOCUMENTI_ATTESI_ACQUISTO: dict[TipoDocumento, str] = {
    TipoDocumento.VISURA_CATASTALE: "identifica l'immobile e verifica l'intestazione catastale",
    TipoDocumento.PLANIMETRIA: "necessaria per la dichiarazione di conformità catastale in atto",
    TipoDocumento.APE: "obbligatoria fin dagli annunci e da allegare/menzionare in atto",
    TipoDocumento.VISURA_IPOTECARIA: "verifica ipoteche, pignoramenti o altre formalità pregiudizievoli",
    TipoDocumento.ATTO_DI_PROVENIENZA: "verifica la provenienza (compravendita/successione/donazione) e la catena di proprietà",
    TipoDocumento.CERTIFICATO_AGIBILITA: "attesta i requisiti di sicurezza/igiene; la sua assenza va segnalata anche se non blocca la vendita",
    TipoDocumento.TITOLO_EDILIZIO: "verifica la conformità urbanistica (stato legittimo) dell'immobile",
    TipoDocumento.RELAZIONE_TECNICA_INTEGRATA: "è lo strumento con cui l'agente adempie all'obbligo di verifica/informazione sulla conformità (art. 1759 c.c., Cass. 24534/2022); senza, va dichiarata esplicitamente l'assenza di verifica",
}

DOCUMENTI_ATTESI_AFFITTO: dict[TipoDocumento, str] = {
    TipoDocumento.VISURA_CATASTALE: "verifica l'intestazione e l'identificazione catastale dell'immobile",
    TipoDocumento.APE: "obbligatoria da allegare al contratto di locazione (salvo specifiche esenzioni)",
    TipoDocumento.REGOLAMENTO_CONDOMINIO: "verifica eventuali limitazioni d'uso opponibili al conduttore",
}


def documenti_mancanti(fascicolo: Fascicolo) -> list[tuple[TipoDocumento, str]]:
    """Confronta i documenti presenti nel fascicolo con la checklist attesa per
    il tipo di transazione, e ritorna quelli mancanti con la spiegazione del
    perché servono.
    """
    attesi = DOCUMENTI_ATTESI_AFFITTO if fascicolo.tipo_transazione == "affitto" else DOCUMENTI_ATTESI_ACQUISTO
    presenti_tipi = {
        d.tipo_documento for d in fascicolo.tutti_i_documenti() if hasattr(d, "tipo_documento")
    }
    return [(tipo, motivo) for tipo, motivo in attesi.items() if tipo not in presenti_tipi]


def report_completezza_campi(fascicolo: Fascicolo) -> list[MissingInfoReport]:
    """Estende documenti_mancanti() (che opera a livello di "manca l'intero
    documento") al livello di singolo campo: per ogni documento GIÀ presente
    nel fascicolo, dice quali campi essenziali/accessori risultano comunque
    vuoti nell'estrazione (schemas.campi_essenziali/campi_accessori via
    consistency.generate_missing_info_questions).

    Utile per un report di completezza fascicolo: "il documento X c'è ma è
    stato estratto solo parzialmente" è un'informazione diversa (e spesso più
    urgente, perché il documento richiesto al proprietario è già arrivato) da
    "il documento X manca del tutto".
    """
    return [
        generate_missing_info_questions(doc, property_id=fascicolo.property_id,
                                        document_id=fascicolo.document_id_for(doc))
        for doc in fascicolo.tutti_i_documenti()
        if hasattr(doc, "tipo_documento")
    ]


