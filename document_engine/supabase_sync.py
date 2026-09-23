from integrations.supabase.fact_mapper import map_extraction_to_facts


def sync_document_result_to_supabase(
    document_result,
    property_id,
    document_id,
    analysis_result_id,
    source_document
):
    """
    Sincronizza il risultato del document engine
    con il database SmartBuy.

    Salva:
    - property_facts
    - fact_provenance
    """

    extraction = (
        document_result
        .get("extraction", {})
        .get("fields", {})
    )


    if not extraction:
        return {
            "status": "skipped",
            "reason": "Nessun campo estratto"
        }


    saved = map_extraction_to_facts(
        extraction_result=extraction,
        property_id=property_id,
        document_id=document_id,
        analysis_result_id=analysis_result_id,
        source_document=source_document
    )


    return {
        "status": "success",
        "facts_saved": len(saved),
        "details": saved
    }