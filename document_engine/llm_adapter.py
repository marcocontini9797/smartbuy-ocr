"""
SmartBuy LLM Adapter v1

Interfaccia astratta per modelli linguistici.
"""


from __future__ import annotations


from typing import Protocol





class LLMProvider(Protocol):


    def generate(

        self,

        context: dict

    ) -> dict:

        ...





class MockLLMAdapter:


    """
    Provider temporaneo per test.
    Sostituibile con API reali.
    """


    def generate(

        self,

        context: dict

    ):


        return {

            "answer":

            "Analisi completata utilizzando "

            "le informazioni disponibili.",


            "claims":[

                {

                "text":

                "È presente una criticità.",

                "source_required":

                True

                }

            ],


            "confidence":0.90

        }