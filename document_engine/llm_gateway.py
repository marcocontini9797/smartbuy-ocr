"""
SmartBuy LLM Gateway v2

Gestisce:
- prompt versioning
- chiamata modello
- audit logging
"""


from __future__ import annotations


from core.llm_gateway_models import (

    LLMRequest,

    LLMResponse

)


from core.llm_audit_models import (

    LLMAuditRecord

)





class LLMGateway:



    def __init__(

        self,

        prompt_manager,

        provider,

        audit_repository=None

    ):


        self.prompt_manager = prompt_manager

        self.provider = provider

        self.audit_repository = audit_repository





    def complete(

        self,

        task: str,

        context: dict,

        property_id: int,

        user_query: str

    ):


        # recupero prompt

        prompt = self.prompt_manager.get(

            task,

            "1.0"

        )





        request = LLMRequest(

            task=task,

            prompt_version=prompt.version,

            context=context

        )





        # chiamata modello

        result = self.provider.generate(

            request

        )





        response = LLMResponse(

            answer=result["answer"],

            model=result.get(

                "model",

                "unknown"

            ),

            prompt_version=prompt.version,

            confidence=result.get(

                "confidence",

                0

            ),

            usage=result.get(

                "usage",

                {}

            )

        )





        # AUDIT AUTOMATICO

        if self.audit_repository:



            audit = LLMAuditRecord(

                property_id=property_id,

                user_query=user_query,

                task=task,

                prompt_version=prompt.version,

                model=response.model,

                answer=response.answer,

                confidence=response.confidence,

                grounded=result.get(

                    "grounded",

                    False

                ),

                input_tokens=response.usage.get(

                    "input_tokens",

                    0

                ),

                output_tokens=response.usage.get(

                    "output_tokens",

                    0

                )

            )



            self.audit_repository.save(

                audit.model_dump()

            )





        return response