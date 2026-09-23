from document_engine.task_engine import generate_tasks

from core.models import Issue





issues = [

    Issue(

        category="ownership",

        type="ownership_conflict",

        severity="high",

        title="Disallineamento intestatario",

        description="Visura e atto non coincidono.",

        metadata={

            "priority":

                "high"

        }

    ),


    Issue(

        category="documentation",

        type="missing_document",

        severity="medium",

        title="Manca visura ipotecaria",

        description="Documento necessario.",

        metadata={

            "priority":

                "medium"

        }

    )

]





tasks = generate_tasks(

    issues

)





for task in tasks:

    print("\n================")

    print(

        task.model_dump_json(

            indent=2

        )

    )