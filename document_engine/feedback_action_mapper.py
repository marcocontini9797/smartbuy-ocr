"""
SmartBuy Feedback Action Mapper v1

Definisce le azioni disponibili
nella sidebar agente.

Collega:

Action Sidebar
        ↓
FeedbackEvent
        ↓
Feedback System
"""


from core.action_models import ActionFeedbackOption





# ==================================================
# ISSUE ACTIONS
# ==================================================


def get_issue_actions():

    return [

        ActionFeedbackOption(

            label="Conferma problema",

            feedback_action="CONFIRM",

            description=(

                "Il problema individuato "

                "è corretto."

            )

        ),


        ActionFeedbackOption(

            label="Segnala falso positivo",

            feedback_action="NOT_RELEVANT",

            description=(

                "Il problema non è "

                "corretto."

            )

        ),


        ActionFeedbackOption(

            label="Segna come risolto",

            feedback_action="RESOLVED",

            description=(

                "Il problema è stato "

                "risolto."

            )

        )

    ]





# ==================================================
# DOCUMENT ACTIONS
# ==================================================


def get_document_actions():

    return [

        ActionFeedbackOption(

            label="Documento caricato",

            feedback_action="LINK_DOCUMENT",

            description=(

                "Collega il nuovo "

                "documento."

            )

        ),


        ActionFeedbackOption(

            label="Documento ancora mancante",

            feedback_action="STILL_MISSING",

            description=(

                "Il documento non è "

                "disponibile."

            )

        )

    ]





# ==================================================
# FACT ACTIONS
# ==================================================


def get_fact_actions():

    return [

        ActionFeedbackOption(

            label="Conferma dato",

            feedback_action="CONFIRM",

            description=(

                "Il dato estratto "

                "è corretto."

            )

        ),


        ActionFeedbackOption(

            label="Correggi dato",

            feedback_action="CORRECT",

            description=(

                "Modifica il valore "

                "estratto."

            )

        )

    ]