"""
SmartBuy Event Bus v1

Sistema interno di pubblicazione
e sottoscrizione eventi.
"""


from __future__ import annotations





class EventBus:


    def __init__(self):

        self.subscribers = {}





    def subscribe(

        self,

        event_type: str,

        handler

    ):


        if event_type not in self.subscribers:

            self.subscribers[event_type] = []


        self.subscribers[event_type].append(

            handler

        )





    def publish(

        self,

        event

    ):


        handlers = self.subscribers.get(

            event.event_type,

            []

        )


        results = []


        for handler in handlers:

            results.append(

                handler(event)

            )


        return results