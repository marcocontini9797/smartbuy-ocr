"""
SmartBuy Document Engine - Test standalone
"""

import asyncio


from document_engine.ingestion import (
    ingest_document
)


from document_engine.ocr import (
    run_ocr
)



def main():
    FILE = (
        r"C:\Users\Marco\smartbuy-casa-diretta"
        r"\due_diligence_brain\document_analysis"
        r"\visura_demo.pdf"
    )



    # ==============================
    # LOAD FILE
    # ==============================

    with open(FILE, "rb") as f:
        content = f.read()



    print("\n========== INGEST ==========")



    document = ingest_document(

        filename="visura_demo.pdf",

        content=content

    )



    print(document.metadata)



    print("\n========== OCR ==========")



    ocr_result = asyncio.run(

        run_ocr(

            content,

            ".pdf"

        )

    )



    print(
        "Pagine:",
        len(ocr_result.pages)
    )


    print(
        "Confidence OCR:",
        ocr_result.confidence
    )


    print(
        "\nTESTO ESTRATTO:"
    )


    print(
        ocr_result.full_text[:3000]
    )

if __name__ == "__main__":
    main()
