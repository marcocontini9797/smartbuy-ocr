"""
SmartBuy Prompt Models v1

Gestione prompt versionati.
"""


from __future__ import annotations


from typing import Any


from pydantic import BaseModel, Field





class PromptTemplate(BaseModel):


    name: str


    version: str


    system_prompt: str


    rules: list[str] = Field(

        default_factory=list

    )


    metadata: dict[str, Any] = Field(

        default_factory=dict

    )