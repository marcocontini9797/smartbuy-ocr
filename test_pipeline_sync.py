from document_engine.pipeline_sync import sync_extraction_pipeline


document_result = {

    "document_type": "ape",

    "extraction": {

        "fields": {

            "energy_class": {

                "value": "B",
                "confidence": 0.98,
                "source_page": 2,
                "source_text": "Classe energetica B"

            },

            "epgl": {

                "value": 74,
                "confidence": 0.97,
                "source_page": 2,
                "source_text": "EPgl 74 kWh/m² anno"

            }

        }

    }

}


result = sync_extraction_pipeline(

    document_result=document_result,

    property_id=16,

    document_id=2,

    analysis_result_id="5a61117d-ee69-45a4-b885-d7b29f648226",

    source_document="APE_test.pdf"

)


print(result)