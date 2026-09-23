import asyncio


from document_engine.ingestion import ingest_document

from document_engine.ocr import run_ocr

from document_engine.classifier import (
    classify_with_validation
)



FILE = (
    r"C:\Users\Marco\smartbuy-casa-diretta"
    r"\due_diligence_brain\document_analysis"
    r"\visura_demo.pdf"
)



with open(FILE, "rb") as f:
    content = f.read()



document = ingest_document(
    filename="documento_sconosciuto.pdf",
    content=content
)



ocr = asyncio.run(
    run_ocr(
        content,
        ".pdf"
    )
)



result = classify_with_validation(

    ocr.full_text,

    document.metadata

)



print("\n========== CLASSIFICATION ==========")

print(
    result.model_dump_json(
        indent=2
    )
)