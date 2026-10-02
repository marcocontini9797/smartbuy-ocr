"""SmartBuy Agent API routes: ask natural-language questions about one fascicolo.

The agent subsystem (document_engine/agent_service.py and friends) shipped
with no real retrieval, no real LLM gateway, and — critically — this route
originally took property_id/user_id as plain body fields with no session
check, meaning anyone who guessed a property_id could read another agent's
fascicolo through it. Fixed here: property_id comes from the URL (same
pattern as every other property route), the caller is authenticated via
user_client, and get_property() enforces the same ownership check as the
rest of the app before any retrieval happens.

No module-level singleton: retrieval must run through the CALLER'S OWN
Supabase client so RLS scopes reads to their own properties, so the service
is built fresh per request instead of configured once at startup.
"""

from fastapi import APIRouter, Depends, HTTPException

from api_models import AgentAnswerFeedbackRequest, AgentAskRequest, AgentAskResponse
from api.property_routes import get_property
from api.session import user_client
from document_engine.agent_service import SmartBuyAgentService
from document_engine.agent_retrieval_supabase import SupabaseAgentRetrieval
from document_engine.agent_llm_gateway import AgentLLMGateway

router = APIRouter(prefix="/api/v1", tags=["agent"])


@router.post("/properties/{property_id}/agent/ask", response_model=AgentAskResponse)
def ask_agent(property_id: int, request: AgentAskRequest, client=Depends(user_client)):
    get_property(property_id, client)  # 404s if the caller doesn't own this property
    retrieval = SupabaseAgentRetrieval(client)
    service = SmartBuyAgentService(retrieval=retrieval, llm_gateway=AgentLLMGateway())
    try:
        result = service.ask(property_id=property_id, question=request.question)
    except Exception as exc:
        raise HTTPException(502, "L'assistente non è riuscito a rispondere: riprova tra poco.") from exc
    if retrieval.last_trace_id:
        try:    # the answer is kept so a quick re-ask can later be recognised as a sign it fell short
            client.table("agent_retrieval_traces").update(
                {"answer": result.answer[:8000], "answer_grounded": bool(result.grounded)}
            ).eq("id", retrieval.last_trace_id).execute()
        except Exception:
            pass
    return AgentAskResponse(
        answer=result.answer, confidence=result.confidence, grounded=result.grounded,
        risk_level=result.risk_level, sources=result.sources, trace_id=retrieval.last_trace_id,
    )


def _valid_trace(value: str | None) -> str | None:
    import uuid
    try:
        return str(uuid.UUID(value)) if value else None
    except ValueError:
        return None


@router.post("/properties/{property_id}/agent/feedback", status_code=201)
def rate_agent_answer(property_id: int, request: AgentAnswerFeedbackRequest, client=Depends(user_client)):
    """Thumbs up/down on an answer; the negative ones feed the retrieval test set and the weekly digest."""
    get_property(property_id, client)
    if request.rating not in (1, -1):
        raise HTTPException(422, "Valutazione non valida")
    try:
        client.table("agent_answer_feedback").insert({
            "property_id": property_id, "question": request.question.strip(), "answer": request.answer,
            "rating": request.rating, "comment": (request.comment or "").strip() or None,
            "grounded": request.grounded, "sources": request.sources, "trace_id": _valid_trace(request.trace_id),
        }).execute()
    except Exception as exc:
        raise HTTPException(503, "Feedback non salvato: riprova tra poco.") from exc
    return {"saved": True}
