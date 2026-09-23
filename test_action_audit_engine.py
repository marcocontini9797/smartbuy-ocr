from document_engine.action_audit_engine import create_audit_event


from core.action_models import ActionItem





action = ActionItem(

    status="green",

    priority="low",

    title="Disallineamento intestatario",

    reason="Problema risolto",

    action_description="Nuova documentazione ricevuta",

    source_type="issue",

    source_reference="ownership_conflict"

)





audit = create_audit_event(

    action,

    "RESOLVED",

    actor_id="agent_001",

    previous_status="red",

    previous_priority="high"

)





print(

    audit.model_dump_json(

        indent=2

    )

)