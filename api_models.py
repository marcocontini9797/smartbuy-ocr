"""
SmartBuy API Models v1
"""

from pydantic import BaseModel



class AgentAskRequest(BaseModel):

    property_id: int

    question: str

    user_id: str | None = None





class AgentAskResponse(BaseModel):

    answer: str

    confidence: float

    grounded: bool

    risk_level: str | None

    sources: list