"""
SmartBuy Document Engine - Extraction Test

Test completo:

PDF
 ↓
INGEST
 ↓
OCR
 ↓
CLASSIFIER
 ↓
ROUTER
 ↓
EXTRACTION + VERIFICATION
 ↓
SUPABASE SYNC
"""


import asyncio


from document_engine.ingestion import (
    ingest_document
)


from document_engine.ocr import (
    run_ocr
)


from document_engine.classifier import (
    classify_with_validation
)


from document_engine.router import (
    build_document_result
)



FILE = (
    r"C:\Users\Marco\smartbuy-casa-diretta"
    r"\due_diligence_brain\document_analysis"
    r"\visura_demo.pdf"
)



# ==========================================
# SMARTBUY DATABASE REFERENCES
# ==========================================

PROPERTY_ID = 16

DOCUMENT_ID = 2

ANALYSIS_RESULT_ID = (
    "5a61117d-ee69-45a4-b885-d7b29f648226"
)

SOURCE_DOCUMENT = "visura_demo.pdf"





# ==========================================
# LOAD FILE
# ==========================================

with open(FILE, "rb") as f:

    content = f.read()





# ==========================================
# INGEST
# ==========================================

document = ingest_document(

    filename=SOURCE_DOCUMENT,

    content=content

)





# ==========================================
# OCR
# ==========================================

ocr = asyncio.run(

    run_ocr(

        content,

        ".pdf"

    )

)





# ==========================================
# CLASSIFICATION
# ==========================================

classification = classify_with_validation(

    ocr.full_text,

    document.metadata

)



print("\n========== CLASSIFICATION ==========")


print(

    classification.model_dump_json(

        indent=2

    )

)





# ==========================================
# EXTRACTION + SUPABASE SYNC
# ==========================================

result = build_document_result(

    ocr.full_text,

    classification,

    property_id=PROPERTY_ID,

    document_id=DOCUMENT_ID,

    analysis_result_id=ANALYSIS_RESULT_ID,

    source_document=SOURCE_DOCUMENT

)





print("\n========== EXTRACTION RESULT ==========")


print(result)