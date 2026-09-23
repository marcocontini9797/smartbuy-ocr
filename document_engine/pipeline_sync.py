from .supabase_sync import sync_document_result_to_supabase


def sync_extraction_pipeline(
    document_result,
    property_id,
    document_id,
    analysis_result_id,
    source_document
):
    """
    Sincronizza il risultato completo del document engine
    verso Supabase.

    Salva:
    - property_facts
    - fact_provenance
    """

    try:

        result = sync_document_result_to_supabase(
            document_result=document_result,
            property_id=property_id,
            document_id=document_id,
            analysis_result_id=analysis_result_id,
            source_document=source_document
        )

        return {
            "sync_status": "completed",
            "supabase_result": result
        }


    except Exception as e:

        return {
            "sync_status": "failed",
            "error": str(e)
        }