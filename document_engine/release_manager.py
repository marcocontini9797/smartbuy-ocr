"""
SmartBuy Release Manager v1

Gestione versioni agente.
"""

from __future__ import annotations


from core.agent_version_models import (

    AgentVersion

)





class ReleaseManager:



    def __init__(self):

        self.versions = []





    def create_release(

        self,

        version: str,

        prompt_version: str,

        knowledge_version: str,

        model_version: str,

        changes:list[str]

    ):


        release = AgentVersion(

            version=version,

            status="draft",

            prompt_version=prompt_version,

            knowledge_version=knowledge_version,

            model_version=model_version,

            changes=changes

        )


        self.versions.append(

            release

        )


        return release





    def approve(

        self,

        version:str

    ):


        for item in self.versions:


            if item.version == version:


                item.status="production"


                return item



        return None