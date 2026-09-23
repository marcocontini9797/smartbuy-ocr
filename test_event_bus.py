from core.event_models import SmartBuyEvent


from document_engine.event_bus import EventBus





bus = EventBus()





def risk_engine(event):

    return {

        "engine":"risk",

        "action":

            f"Ricalcolo rischio per {event.entity_id}"

    }





def action_engine(event):

    return {

        "engine":"actions",

        "action":

            f"Aggiornamento azioni per {event.entity_id}"

    }





bus.subscribe(

    "FACT_CHANGED",

    risk_engine

)



bus.subscribe(

    "FACT_CHANGED",

    action_engine

)





event = SmartBuyEvent(

    event_type="FACT_CHANGED",

    property_id=16,

    entity_type="FACT",

    entity_id="FACT001",

    payload={

        "old":"Rossi Giovanni",

        "new":"Bianchi Mario"

    }

)





results = bus.publish(

    event

)





for result in results:

    print(result)