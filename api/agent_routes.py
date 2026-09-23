"""
SmartBuy Agent API Routes v1
"""


from fastapi import APIRouter, HTTPException


from api_models import (
    AgentAskRequest,
    AgentAskResponse
)





router = APIRouter()



agent_service = None





def configure_agent_service(service):

    global agent_service

    agent_service = service





@router.post(
    "/agent/ask",
    response_model=AgentAskResponse
)
def ask_agent(

    request: AgentAskRequest

):

    if agent_service is None:
        raise HTTPException(
            status_code=503,
            detail="SmartBuy agent service is not configured"
        )


    result = agent_service.ask(

        property_id=request.property_id,

        question=request.question,

        user_id=request.user_id

    )


    return AgentAskResponse(

        answer=result.answer,

        confidence=result.confidence,

        grounded=result.grounded,

        risk_level=result.risk_level,

        sources=result.sources

    )
