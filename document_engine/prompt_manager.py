"""
SmartBuy Prompt Manager v1

Caricamento e gestione prompt.
"""


from __future__ import annotations


from core.prompt_models import PromptTemplate





class PromptManager:



    def __init__(

        self

    ):

        self.prompts = {}





    def register(

        self,

        prompt: PromptTemplate

    ):


        key = (

            prompt.name,

            prompt.version

        )


        self.prompts[key] = prompt





    def get(

        self,

        name: str,

        version: str

    ) -> PromptTemplate:


        return self.prompts[

            (

                name,

                version

            )

        ]