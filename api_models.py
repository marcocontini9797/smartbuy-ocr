"""
SmartBuy API Models v1
"""

from pydantic import BaseModel, Field



class AgentAskRequest(BaseModel):

    question: str = Field(min_length=1, max_length=1000)





class AgentAskResponse(BaseModel):

    answer: str

    confidence: float

    grounded: bool

    risk_level: str | None

    sources: list