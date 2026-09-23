"""
SmartBuy Supabase Repository

Layer di accesso dati.
Gestisce:

- salvataggio documenti
- salvataggio analisi
- recupero fascicolo
"""

from datetime import datetime
import json


from .client import supabase





# ==================================================
# DOCUMENTS
# ==================================================


def save_document(

    document_data: dict

):

    """
    Salva un documento nella tabella documents
    """

    response = (

        supabase

        .table("documents")

        .insert(document_data)

        .execute()

    )


    return response.data





# ==================================================
# DOCUMENT ANALYSIS
# ==================================================


def save_document_analysis(

    analysis_data: dict

):

    """
    Salva il risultato dell'analisi documento
    """

    response = (

        supabase

        .table("document_analyses")

        .insert(analysis_data)

        .execute()

    )


    return response.data





# ==================================================
# PROPERTY FACTS
# ==================================================


def save_property_fact(

    fact_data: dict

):

    """
    Salva un'informazione estratta sull'immobile
    """

    response = (

        supabase

        .table("property_facts")

        .insert(fact_data)

        .execute()

    )


    return response.data





# ==================================================
# GET PROPERTY DOCUMENTS
# ==================================================


def get_property_documents(

    property_id: int

):

    """
    Recupera tutti i documenti di un immobile
    """

    response = (

        supabase

        .table("documents")

        .select("*")

        .eq(

            "property_id",

            property_id

        )

        .execute()

    )


    return response.data





# ==================================================
# GET PROPERTY
# ==================================================


def get_property(

    property_id: int

):


    response = (

        supabase

        .table("sb_properties")

        .select("*")

        .eq(

            "id",

            property_id

        )

        .single()

        .execute()

    )


    return response.data





# ==================================================
# BUILD FASCICOLO DATA
# ==================================================


def get_fascicolo_data(

    property_id: int

):


    property = get_property(

        property_id

    )


    documents = get_property_documents(

        property_id

    )


    return {


        "property":

            property,


        "documents":

            documents

    }