"""
SmartBuy Task Engine v1

Trasforma Issue in attività operative
per agente immobiliare.
"""


from __future__ import annotations


from core.models import Issue


from core.task_models import Task





# ==================================================
# TASK RULES
# ==================================================


TASK_RULES = {


    "ownership_conflict": {


        "task_type":

            "verification",


        "title":

            "Verificare titolarità immobile",


        "description":

            "Confrontare intestatari catastali e atto di provenienza.",


        "blocking":

            True

    },



    "missing_document": {


        "task_type":

            "request_document",


        "title":

            "Richiedere documento mancante",


        "description":

            "Richiedere il documento necessario al proprietario.",


        "blocking":

            False

    },



    "cadastral_conflict": {


        "task_type":

            "technical_check",


        "title":

            "Verificare conformità catastale",


        "description":

            "Confrontare dati catastali e documentazione tecnica.",


        "blocking":

            True

    },



    "urbanistic_conflict": {


        "task_type":

            "technical_check",


        "title":

            "Richiedere verifica urbanistica",


        "description":

            "Richiedere controllo della conformità edilizia.",


        "blocking":

            True

    }

}





# ==================================================
# SINGLE TASK
# ==================================================


def issue_to_task(

    issue: Issue

) -> Task:


    rule = TASK_RULES.get(

        issue.type,

        {

            "task_type":

                "review",

            "title":

                "Verificare criticità",

            "description":

                "Analizzare il problema rilevato.",

            "blocking":

                False

        }

    )



    return Task(

        task_type=rule["task_type"],

        title=rule["title"],

        description=rule["description"],

        priority=issue.metadata.get(

            "priority",

            "medium"

        ),

        blocking=rule["blocking"],

        source_issue=issue.type

    )





# ==================================================
# MULTIPLE TASKS
# ==================================================


def generate_tasks(

    issues: list[Issue]

) -> list[Task]:


    return [

        issue_to_task(issue)

        for issue in issues

    ]