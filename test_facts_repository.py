from integrations.supabase.facts_repository import save_extracted_fact


result = save_extracted_fact(
    analysis_result_id="5a61117d-ee69-45a4-b885-d7b29f648226",
    property_id=16,
    document_id=2,
    fact_name="energy_class_test",
    fact_value="B",
    source_document="APE_test.pdf",
    source_page=2,
    source_text="Classe energetica B",
    confidence=0.95
)


print(result)