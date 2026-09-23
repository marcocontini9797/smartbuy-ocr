from document_engine.feedback_engine import create_feedback





# Caso 1:
# l'agente conferma un problema


feedback_1 = create_feedback(

    source_type="issue",

    source_id="CROSS-001",

    feedback_type="accepted",

    is_correct=True,

    impact="high",

    created_by="agente_demo"

)





print("================")

print(

    feedback_1.model_dump_json(

        indent=2

    )

)







# Caso 2:
# l'agente corregge un dato estratto


feedback_2 = create_feedback(

    source_type="fact",

    source_id="FACT-ENERGY-001",

    feedback_type="corrected",

    is_correct=False,

    corrected_value="A3",

    agent_comment=(

        "La classe energetica corretta "

        "è A3."

    ),

    created_by="agente_demo"

)





print("================")

print(

    feedback_2.model_dump_json(

        indent=2

    )

)