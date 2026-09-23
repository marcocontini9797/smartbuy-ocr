"""
SmartBuy Fact Mapper v2

Converte i risultati di estrazione
in oggetti standard Core.Fact.

Pipeline:

Extraction
    ↓
Fact Mapper
    ↓
Core Fact Model
    ↓
Supabase Repository
"""


from __future__ import annotations


from typing import Any


from core.models import Fact





# ==================================================
# SINGLE FACT BUILDER
# ==================================================


def build_fact(

    name: str,

    value: Any,

    confidence: float = 0.0,

    category: str = "document",

    source_type: str = "document",

    metadata: dict | None = None

) -> Fact:


    return Fact(

        name=name,

        value=value,

        category=category,

        source_type=source_type,

        confidence=confidence,

        metadata=metadata or {}

    )





# ==================================================
# EXTRACTION DICT → FACTS
# ==================================================


def map_extraction_to_facts(

    extracted_data: dict,

    confidence_map: dict | None = None,

    category: str = "document"

) -> list[Fact]:


    facts = []


    confidence_map = confidence_map or {}



    for key, value in extracted_data.items():


        confidence = confidence_map.get(

            key,

            0.95

        )


        facts.append(

            build_fact(

                name=key,

                value=value,

                confidence=confidence,

                category=category

            )

        )



    return facts





# ==================================================
# CORE FACT → SUPABASE FORMAT
# ==================================================


def fact_to_supabase_payload(

    fact: Fact,

    document_id: int,

    source_document: str | None = None

) -> dict:


    return {


        "fact_name":

            fact.name,


        "fact_value":

            {

                "value":

                    fact.value

            },


        "fact_category":

            fact.category,


        "source_type":

            fact.source_type,


        "source_document_id":

            document_id,


        "confidence_score":

            fact.confidence,


        "verification_status":

            fact.verification_status,


        "metadata":

            fact.metadata

    }





# ==================================================
# TEST HELPER
# ==================================================


def debug_print_facts(

    facts: list[Fact]

):


    for fact in facts:


        print(

            fact.model_dump_json(

                indent=2

            )

        )