"""Read API for the SmartBuy agent workspace.

The router only composes canonical Fiverr/Supabase entities. It does not create
parallel persistence models or duplicate tables.
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field
from api.session import user_client
from api.intelligence_service import build_property_intelligence


router = APIRouter(prefix="/api/v1", tags=["workspace"])


def _rows(client, table: str, property_id: int) -> list[dict]:
    try:
        response = client.table(table).select("*").eq("property_id", property_id).execute()
        return response.data or []
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Data service unavailable") from exc


def _optional_rows(client, table: str, property_id: int) -> list[dict]:
    """Read additive operational tables while migration rollout is in progress."""
    try:
        response = client.table(table).select("*").eq("property_id", property_id).execute()
        return response.data or []
    except Exception:
        return []


class NewProperty(BaseModel):
    address: str = Field(min_length=3, max_length=200)
    city: str = Field(min_length=2, max_length=100)
    asking_price: float | None = Field(default=None, ge=0)
    surface_m2: float | None = Field(default=None, gt=0, le=100000)
    rooms: int | None = Field(default=None, ge=0, le=100)
    floor: int | None = Field(default=None, ge=-5, le=200)


@router.post("/properties", status_code=201)
def create_property(payload: NewProperty, client=Depends(user_client)):
    data = {key: value for key, value in payload.model_dump().items() if value is not None}
    data["address"], data["city"] = payload.address.strip(), payload.city.strip()
    try:
        response = client.table("properties").insert({**data, "user_id": client.smartbuy_user_id}).execute()
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Unable to create the property") from exc
    if not response.data:
        raise HTTPException(status_code=502, detail="Unable to create the property")
    return response.data[0]


@router.get("/properties")
def list_properties(limit: int = Query(100, ge=1, le=500), client=Depends(user_client)):
    try:
        response = client.table("properties").select("*").eq("user_id", client.smartbuy_user_id).order("id", desc=True).limit(limit).execute()
        return {"items": response.data or [], "count": len(response.data or [])}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Data service unavailable") from exc


@router.get("/properties/{property_id}")
def get_property(property_id: int, client=Depends(user_client)):
    try:
        response = client.table("properties").select("*").eq("id", property_id).eq("user_id", client.smartbuy_user_id).limit(1).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Property not found")
        return response.data[0]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Data service unavailable") from exc


@router.get("/properties/{property_id}/workspace")
def get_property_workspace(property_id: int, client=Depends(user_client)):
    """Return the canonical property lineage used by the frontend."""
    property_record = get_property(property_id, client)
    analyses = _rows(client, "document_analyses", property_id)
    document_ids = list({item["document_id"] for item in analyses if item.get("document_id") is not None})
    try:
        documents = (client.table("documents").select("*").in_("id", document_ids).execute().data or []) if document_ids else []
    except Exception as exc:
        raise HTTPException(502, "Document service unavailable") from exc
    facts = _rows(client, "property_facts", property_id)
    evidence = _rows(client, "property_evidence", property_id)
    issues = _rows(client, "property_issues", property_id)
    runs = _optional_rows(client, "smartbuy_analysis_runs", property_id)
    operational_evidence = _optional_rows(client, "smartbuy_operational_evidence", property_id)
    document_requests = _optional_rows(client, "smartbuy_document_requests", property_id)
    return {
        "property": property_record,
        "documents": documents,
        "analyses": analyses,
        "facts": facts,
        "evidence": evidence,
        "issues": issues,
        "analysis_runs": runs,
        "operational_evidence": operational_evidence,
        "document_requests": document_requests,
        "summary": {
            "documents": len(documents),
            "facts": len(facts),
            "evidence": len(evidence),
            "open_issues": sum(1 for item in issues if str(item.get("status", "open")).lower() not in {"resolved", "closed"}),
            "analysis_runs": len(runs),
            "open_document_requests": sum(1 for item in document_requests if item.get("status") in {"open", "sent"}),
        },
    }


@router.get("/properties/{property_id}/intelligence")
def get_property_intelligence(property_id: int, client=Depends(user_client)):
    """Return the real core profile and RiskEnginePOC report for one owned property."""
    property_record = get_property(property_id, client)
    analyses = _rows(client, "document_analyses", property_id)
    facts = _rows(client, "property_facts", property_id)
    document_ids = list({row["document_id"] for row in analyses if row.get("document_id") is not None})
    try:
        documents = client.table("documents").select("*").in_("id", document_ids).execute().data or [] if document_ids else []
        provenance_ids = list({row["provenance_id"] for row in facts if row.get("provenance_id") is not None})
        provenance = client.table("fact_provenance").select("*").in_("id", provenance_ids).execute().data or [] if provenance_ids else []
    except Exception as exc:
        raise HTTPException(502, "Intelligence lineage unavailable") from exc
    return build_property_intelligence(
        property_record=property_record,
        facts=facts,
        documents=documents,
        analyses=analyses,
        provenance=provenance,
    )

