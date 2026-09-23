from document_engine.release_manager import (

    ReleaseManager

)





manager = ReleaseManager()





release = manager.create_release(

    version="1.1",

    prompt_version="1.1",

    knowledge_version="1.0",

    model_version="gpt-x",


    changes=[

        "Migliorato recupero evidenze",

        "Aggiornato prompt proprietà"

    ]

)





print("================ DRAFT ================")

print(

    release.model_dump_json(

        indent=2

    )

)





approved = manager.approve(

    "1.1"

)





print("================ PRODUCTION ================")

print(

    approved.model_dump_json(

        indent=2

    )

)