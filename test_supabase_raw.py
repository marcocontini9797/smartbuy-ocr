from integrations.supabase.client import supabase


print("\n========== SB_PROPERTIES ==========")

properties = (
    supabase
    .table("sb_properties")
    .select("*")
    .eq("id", 1)
    .execute()
)

print(properties.data)


print("\n========== DOCUMENTS ==========")

documents = (
    supabase
    .table("documents")
    .select(
        "id,"
        "fascicolo_id,"
        "file_name,"
        "document_type,"
        "processing_status,"
        "created_at"
    )
    .limit(20)
    .execute()
)

print(documents.data)


print("\n========== DOCUMENT_ANALYSES ==========")

analyses = (
    supabase
    .table("document_analyses")
    .select(
        "id,"
        "property_id,"
        "document_id,"
        "document_name,"
        "document_type,"
        "confidence_score,"
        "analysis_status"
    )
    .limit(20)
    .execute()
)

print(analyses.data)