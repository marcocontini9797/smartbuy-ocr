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


class AgentAnswerFeedbackRequest(BaseModel):

    question: str = Field(min_length=1, max_length=1000)

    answer: str = Field(max_length=8000)

    rating: int = Field(description="1 = utile, -1 = sbagliata o inutile")

    comment: str | None = Field(default=None, max_length=1000)

    grounded: bool | None = None

    sources: list = Field(default_factory=list, max_length=20)
