"""
SmartBuy Evidence Mapper v1

Converte le evidenze generate
dai motori interni nel modello
standard core.Evidence.
"""


from __future__ import annotations


from typing import Any


from core.models import Evidence





# ==================================================
# SINGLE EVIDENCE BUILDER
# ==================================================


def build_evidence(

    document: str,

    page: int | None = None,

    text: str | None = None,

    confidence: float = 0.0,

    metadata: dict[str, Any] | None = None

) -> Evidence:


    return Evidence(

        document=document,

        page=page,

        text=text,

        confidence=confidence,

        metadata=metadata or {}

    )





# ==================================================
# DICT → EVIDENCE
# ==================================================


def map_dict_to_evidence(

    evidence_data: dict

) -> Evidence:


    return build_evidence(

        document=evidence_data.get(

            "document",

            "unknown"

        ),

        page=evidence_data.get(

            "page"

        ),

        text=evidence_data.get(

            "text"

        ),

        confidence=evidence_data.get(

            "confidence",

            0.0

        ),

        metadata={

            k: v

            for k, v in evidence_data.items()

            if k not in [

                "document",

                "page",

                "text",

                "confidence"

            ]

        }

    )





# ==================================================
# LIST CONVERSION
# ==================================================


def map_evidence_list(

    evidence_list: list[dict]

) -> list[Evidence]:


    return [

        map_dict_to_evidence(e)

        for e in evidence_list

    ]





# ==================================================
# DEBUG
# ==================================================


def debug_print_evidence(

    evidence: list[Evidence]

):


    for item in evidence:


        print(

            item.model_dump_json(

                indent=2

            )

        )