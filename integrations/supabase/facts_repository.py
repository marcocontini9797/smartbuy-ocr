"""
SmartBuy Facts Repository v2

Gestione standardizzata dei Fact.

Pipeline:

Extraction
    ↓
core.Fact
    ↓
Fact Repository
    ↓
fact_provenance
    ↓
property_facts
    ↓
Supabase
"""


from datetime import datetime


from .client import supabase


from core.models import Fact





# ==================================================
# CREATE PROVENANCE
# ==================================================


def create_provenance(

    analysis_result_id,

    document_id,

    fact: Fact,

    source_document,

    source_page=None,

    source_text=None,

    property_id=None

):

    """
    Salva la provenienza del fatto estratto.
    """



    data = {


        "analysis_result_id":

            analysis_result_id,


        "document_id":

            document_id,


        "property_id":

            property_id,


        "fact_name":

            fact.name,


        "fact_value":

            {

                "value":

                    fact.value

            },


        "source_type":

            fact.source_type or "document",


        "source_document":

            source_document,


        "source_page":

            source_page,


        "source_text":

            source_text,


        "extraction_method":

            "AI extraction",


        "model_name":

            "OpenAI",


        "model_version":

            "GPT-5",


        "confidence_score":

            str(fact.confidence),


        "verification_status":

            fact.verification_status,


        "created_at":

            datetime.utcnow().isoformat()

    }



    result = (

        supabase

        .table("fact_provenance")

        .insert(data)

        .execute()

    )


    return result.data





# ==================================================
# CREATE PROPERTY FACT
# ==================================================


def create_property_fact(

    property_id,

    document_id,

    provenance_id,

    fact: Fact

):


    """
    Salva il fatto collegato all'immobile.
    """



    data = {


        "property_id":

            property_id,


        "fact_name":

            fact.name,


        "fact_value":

            {

                "value":

                    fact.value

            },


        "fact_category":

            fact.category or "document",


        "source_type":

            fact.source_type or "document",


        "source_document_id":

            document_id,


        "provenance_id":

            provenance_id,


        "confidence_score":

            str(fact.confidence),


        "verification_status":

            fact.verification_status

    }



    result = (

        supabase

        .table("property_facts")

        .insert(data)

        .execute()

    )


    return result.data





# ==================================================
# NEW STANDARD API
# ==================================================


def save_fact(

    analysis_result_id,

    property_id,

    document_id,

    fact: Fact,

    source_document,

    source_page=None,

    source_text=None

):


    """
    Salvataggio standard usando core.Fact.
    """



    provenance = create_provenance(

        analysis_result_id=

            analysis_result_id,

        document_id=

            document_id,

        fact=

            fact,

        source_document=

            source_document,

        source_page=

            source_page,

        source_text=

            source_text,

        property_id=

            property_id

    )



    provenance_id = provenance[0]["id"]



    saved_fact = create_property_fact(

        property_id=

            property_id,

        document_id=

            document_id,

        provenance_id=

            provenance_id,

        fact=

            fact

    )



    return {


        "provenance":

            provenance,


        "fact":

            saved_fact

    }





# ==================================================
# LEGACY COMPATIBILITY
# ==================================================


def save_extracted_fact(

    analysis_result_id,

    property_id,

    document_id,

    fact_name,

    fact_value,

    source_document,

    source_page,

    source_text,

    confidence

):


    """
    Compatibilità con il vecchio sistema.

    Converte automaticamente
    nel nuovo modello Fact.
    """



    fact = Fact(

        name=fact_name,

        value=fact_value,

        category="document",

        source_type="document",

        confidence=confidence

    )



    return save_fact(

        analysis_result_id=

            analysis_result_id,

        property_id=

            property_id,

        document_id=

            document_id,

        fact=

            fact,

        source_document=

            source_document,

        source_page=

            source_page,

        source_text=

            source_text

    )
