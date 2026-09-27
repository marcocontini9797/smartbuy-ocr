"""Personalized request letters: what document_acquisition.py's CATALOGUE
already knows ("this whole document is missing, ask this recipient") plus
what consistency.generate_missing_info_questions knows ("this document is
here but these fields are still empty") — combined into one letter per
recipient, phrased by the AI but grounded only in that structured list.

This wires up a path consistency.py already flagged as open (see the note on
generate_missing_info_questions: "se in futuro si vuole una formulazione più
naturale/contestuale... si può passare l'elenco di campi mancanti a un
prompt"), which nothing called before this module.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from consistency import generate_missing_info_questions
from llm_client import LIGHT_MODEL, free_text_call
from schemas import SCHEMA_REGISTRY, TipoDocumento
from system_prompts import request_letter_system_prompt

# CATALOGUE key (document_acquisition.py) -> TipoDocumento, restricted to the
# document types that have a parsing schema and can therefore surface
# field-level gaps. A key with no entry here only ever shows up as "document
# missing entirely" (document_acquisition.py's own job), never as "present
# but incomplete".
_SCHEMA_BY_CATALOGUE_KEY = {
    "ape": TipoDocumento.APE,
    "visura_catastale": TipoDocumento.VISURA_CATASTALE,
    "planimetria_catastale": TipoDocumento.PLANIMETRIA,
    "ispezione_ipotecaria": TipoDocumento.VISURA_IPOTECARIA,
    "atto_provenienza": TipoDocumento.ATTO_DI_PROVENIENZA,
    "titoli_edilizi": TipoDocumento.TITOLO_EDILIZIO,
    "agibilita": TipoDocumento.CERTIFICATO_AGIBILITA,
    "regolamento_condominiale": TipoDocumento.REGOLAMENTO_CONDOMINIO,
    "verbali_assembleari": TipoDocumento.VERBALE_ASSEMBLEA_CONDOMINIO,
}

_ROLE_LABELS = {
    "seller": "il proprietario/venditore",
    "professional": "il professionista incaricato (es. geometra o tecnico)",
    "administrator": "l'amministratore di condominio",
}


def field_gaps_for_item(document_type_key: str, matching_documents: list[dict[str, Any]],
                        *, property_id: int) -> dict[str, list[str]] | None:
    """Essential/accessory questions still open in the most recently analysed
    document of this catalogue key, or None if the type has no schema, no
    document parses cleanly, or nothing is missing."""
    tipo = _SCHEMA_BY_CATALOGUE_KEY.get(document_type_key)
    model = SCHEMA_REGISTRY.get(tipo) if tipo else None
    if model is None:
        return None
    parsed = None
    for document in sorted(matching_documents, key=lambda d: d.get("created_at") or "", reverse=True):
        fields = document.get("extracted_fields")
        if not isinstance(fields, dict):
            continue
        try:
            parsed = model.model_validate({**fields, "tipo_documento": tipo})
        except Exception:
            continue
        document_id = str(document.get("id"))
        break
    else:
        return None
    report = generate_missing_info_questions(parsed, property_id=str(property_id), document_id=document_id)
    if not report.domande_essenziali and not report.domande_accessorie:
        return None
    return {"essenziali": report.domande_essenziali, "accessorie": report.domande_accessorie}


def content_hash(recipient_role: str, missing_titles: list[str], field_gaps: dict[str, dict[str, list[str]]]) -> str:
    payload = json.dumps(
        {"recipient": recipient_role, "missing": sorted(missing_titles), "gaps": field_gaps},
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compose_request_message(*, recipient_role: str, property_record: dict[str, Any],
                            missing_titles: list[str], field_gaps: dict[str, dict[str, list[str]]]) -> str | None:
    """AI-composed request letter grounded strictly in the given missing-
    document titles and per-document field gaps. Returns None (caller keeps
    the deterministic fallback text) if nothing is missing or the AI call is
    unavailable/fails — never raises, since this always has a safe fallback."""
    if not missing_titles and not field_gaps:
        return None
    address = property_record.get("address") or "N/D"
    city = property_record.get("city") or "N/D"
    lines = [f"Immobile: {address}, {city}",
             f"Destinatario: {_ROLE_LABELS.get(recipient_role, recipient_role)}", ""]
    if missing_titles:
        lines.append("DOCUMENTI COMPLETAMENTE MANCANTI:")
        lines += [f"- {title}" for title in missing_titles]
        lines.append("")
    for title, gaps in field_gaps.items():
        essenziali, accessorie = gaps.get("essenziali", []), gaps.get("accessorie", [])
        if not essenziali and not accessorie:
            continue
        lines.append(f"DOCUMENTO GIA' RICEVUTO MA INCOMPLETO — {title}:")
        lines += [f"- (essenziale) {q}" for q in essenziali]
        lines += [f"- (accessorio) {q}" for q in accessorie]
        lines.append("")
    try:
        return free_text_call(system=request_letter_system_prompt(), user="\n".join(lines),
                              temperature=0.2, model=LIGHT_MODEL).strip()
    except Exception:
        return None
