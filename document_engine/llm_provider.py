"""
SmartBuy LLM Provider v1

Interfaccia astratta
del modello linguistico.
"""


from __future__ import annotations


from core.llm_models import (
    LLMRequest,
    LLMResponse
)


class MockLLMProvider:

    """
    Provider temporaneo.

    Simula una risposta LLM.
    """


    def generate(
        self,
        request: LLMRequest
    ) -> LLMResponse:


        context = request.context


        issues = context.get(
            "issues",
            []
        )


        if issues:

            answer = (
                "Il fascicolo presenta "
                f"{len(issues)} criticità. "
                "È necessario verificare "
                "gli elementi indicati."
            )

        else:

            answer = (
                "Non risultano criticità "
                "nel contesto analizzato."
            )


        sources = [

            source.get("document")

            for source in context.get(
                "sources",
                []
            )

        ]


        return LLMResponse(

            answer=answer,

            sources=sources,

            metadata={

                "provider": "mock"

            }

        )