from document_engine.fact_mapper import (
    map_extraction_to_facts,
    debug_print_facts
)



extracted = {

    "energy_class": "A2",

    "epgl": 74,

    "year": 2018

}



confidence = {

    "energy_class": 0.98,

    "epgl": 0.97,

    "year": 0.95

}



facts = map_extraction_to_facts(

    extracted,

    confidence,

    category="energy"

)



debug_print_facts(

    facts

)