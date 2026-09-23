"""
Estrazione strutturata (leva 2) — versione rinforzata con verifica a due passaggi.

Pipeline:
1. classify_document_type(text): classifica il tipo di documento.
2. extract_document(text, tipo): estrae i campi secondo lo schema Pydantic del tipo,
   usando client.responses.parse(text_format=<Modello>) — lo schema "strict" è
   generato automaticamente dal modello Pydantic, quindi non c'è schema scritto a
   mano che può disallinearsi dal modello.
3. verify_extraction(text, extracted): SECONDO passaggio, indipendente dal primo,
   che rilegge testo + dati estratti e segnala ogni campo non effettivamente
   supportato dal testo (grounding check / chain-of-verification). Questo è il
   principale intervento di "hardening" della leva 2: un singolo passaggio di
   estrazione può allucinare valori plausibili, un passaggio di verifica
   indipendente li intercetta nella maggior parte dei casi.
4. extract_document_verified(text, tipo): combina 2+3 e abbassa automaticamente
   la confidence dei campi segnalati come non supportati, così il missing-info
   detection e il consistency engine "vedono" l'incertezza a valle.

Extra hardening disponibile ma non attivato di default (costa di più in
chiamate API): extract_document_consensus() fa self-consistency, cioè estrae
più volte a temperatura >0 e segnala i campi su cui le estrazioni non
concordano. Utile per documenti particolarmente critici (es. importi elevati)
dove vale la pena pagare qualche chiamata in più.
"""

from __future__ import annotations

from collections import Counter
from typing import Optional

from pydantic import BaseModel

from llm_client import LIGHT_MODEL, structured_call
from schemas import (
    SCHEMA_REGISTRY,
    CampoEstratto,
    ClassificationResult,
    TipoDocumento,
    VerificationResult,
)
from system_prompts import extraction_system_prompt, verification_system_prompt


def classify_document_type(text: str) -> ClassificationResult:
    # Compito relativamente semplice (poche classi, testo spesso auto-esplicativo
    # nelle prime righe): usiamo il modello leggero per contenere i costi senza
    # impatto pratico sulla precisione rispetto al modello di punta.
    return structured_call(
        system=extraction_system_prompt(),
        user=f"Classifica questo documento:\n\n{text}",
        output_model=ClassificationResult,
        temperature=0.0,
        model=LIGHT_MODEL,
    )


def extract_document(text: str, tipo: TipoDocumento) -> BaseModel:
    model_cls = SCHEMA_REGISTRY.get(tipo)
    if model_cls is None:
        raise ValueError(f"Nessuno schema di estrazione registrato per {tipo}")
    return structured_call(
        system=extraction_system_prompt(),
        user=f"Estrai i dati da questo documento ({tipo.value}):\n\n{text}",
        output_model=model_cls,
        temperature=0.0,
    )


def verify_extraction(text: str, extracted: BaseModel) -> VerificationResult:
    """Secondo passaggio indipendente: verifica che i dati estratti siano supportati dal testo."""
    dati_json = extracted.model_dump_json(indent=2, exclude_none=True)
    return structured_call(
        system=verification_system_prompt(),
        user=(
            f"Testo originale del documento:\n\n{text}\n\n"
            f"Dati estratti da verificare:\n\n{dati_json}"
        ),
        output_model=VerificationResult,
        temperature=0.0,
    )


def _apply_verification_penalty(extracted: BaseModel, verification: VerificationResult) -> BaseModel:
    """Abbassa la confidence dei CampoEstratto segnalati come non supportati e
    aggiunge una nota di incertezza leggibile, così l'informazione non si perde
    silenziosamente: consistency.py e il missing-info detection continuano a
    lavorare sullo stesso oggetto Pydantic, solo con dati di incertezza più accurati.
    """
    if verification.tutti_i_campi_supportati:
        return extracted

    data = extracted.model_dump()
    note_extra = []
    for campo_ns in verification.campi_non_supportati:
        note_extra.append(
            f"[verifica] campo '{campo_ns.campo}' non supportato dal testo "
            f"({campo_ns.gravita}): {campo_ns.motivo}"
        )
        # Se il campo penalizzato è un CampoEstratto di primo livello, ne
        # abbassiamo direttamente la confidence.
        top_level_name = campo_ns.campo.split(".")[0]
        val = data.get(top_level_name)
        if isinstance(val, dict) and "confidence" in val:
            val["confidence"] = min(val.get("confidence") or 0.0, 0.2)

    if "note_incertezza" in data:
        data["note_incertezza"] = list(data.get("note_incertezza") or []) + note_extra

    return type(extracted).model_validate(data)


def extract_document_verified(
    text: str, tipo: TipoDocumento
) -> tuple[BaseModel, VerificationResult]:
    """Pipeline consigliata di default: estrai, poi verifica, poi applica la penalità."""
    extracted = extract_document(text, tipo)
    verification = verify_extraction(text, extracted)
    hardened = _apply_verification_penalty(extracted, verification)
    return hardened, verification


def classify_and_extract(
    text: str, verify: bool = True
) -> tuple[ClassificationResult, Optional[BaseModel], Optional[VerificationResult]]:
    """Pipeline completa: classifica, poi estrae (e verifica) se esiste uno schema per quel tipo."""
    classification = classify_document_type(text)
    tipo = classification.tipo_documento
    if tipo not in SCHEMA_REGISTRY:
        return classification, None, None
    if verify:
        extracted, verification = extract_document_verified(text, tipo)
        return classification, extracted, verification
    return classification, extract_document(text, tipo), None


# ---------------------------------------------------------------------------
# Hardening opzionale: self-consistency via campionamento multiplo
# ---------------------------------------------------------------------------

def extract_document_consensus(
    text: str, tipo: TipoDocumento, n_samples: int = 3, temperature: float = 0.4
) -> tuple[BaseModel, dict[str, list]]:
    """Estrae n_samples volte a temperatura >0 e fa "voto di maggioranza" sui
    campi scalari di primo livello. Ritorna il risultato consenso e un log dei
    disaccordi (campo -> valori osservati) per debug/audit.

    Costa n_samples chiamate invece di 1: usalo solo per documenti/campi ad alto
    impatto (es. prezzo di un atto) dove vale la pena pagare la chiamata extra,
    non come default per ogni documento del fascicolo.
    """
    model_cls = SCHEMA_REGISTRY.get(tipo)
    if model_cls is None:
        raise ValueError(f"Nessuno schema di estrazione registrato per {tipo}")

    samples = [
        structured_call(
            system=extraction_system_prompt(),
            user=f"Estrai i dati da questo documento ({tipo.value}):\n\n{text}",
            output_model=model_cls,
            temperature=temperature if i > 0 else 0.0,
        )
        for i in range(n_samples)
    ]

    base = samples[0].model_dump()
    disagreements: dict[str, list] = {}
    for field_name, base_value in list(base.items()):
        if isinstance(base_value, (dict, list)):
            continue  # il voto di maggioranza semplice si applica solo a campi scalari
        values = [getattr(s, field_name) for s in samples]
        if len(set(values)) > 1:
            disagreements[field_name] = values
            most_common_value, _ = Counter(values).most_common(1)[0]
            base[field_name] = most_common_value

    consensus = model_cls.model_validate(base)
    return consensus, disagreements


