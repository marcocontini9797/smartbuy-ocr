from core.models import Fact

from integrations.supabase.facts_repository import save_fact



fact = Fact(

    name="energy_class",

    value="A2",

    category="energy",

    source_type="document",

    confidence=0.98

)



result = save_fact(

    analysis_result_id="5a61117d-ee69-45a4-b885-d7b29f648226",

    property_id=16,

    document_id=2,

    fact=fact,

    source_document="APE_test.pdf",

    source_page=2,

    source_text="Classe energetica A2"

)



print(result)