"""Public, unauthenticated seller/buyer lead-generation quiz.

Every route here is reachable with no user session because this is the
pre-mandate funnel. Requests are accepted only when they come through the
SmartBuy web BFF, authenticated with SMARTBUY_BFF_SECRET.

All Supabase access goes through the privileged backend client because
seller_leads contains personal data and is not directly accessible to
anon/authenticated roles.
"""

from __future__ import annotations

import os
import secrets
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, EmailStr, Field

from document_engine.seller_lead import (
    complexity_factors,
    compose_seller_report,
    full_estimate,
    market_snapshot,
    proximity_snapshot,
    resolve_location,
    territory_snapshot,
    typology_price_range,
    zone_price_range,
)
from integrations.supabase.client import supabase


router = APIRouter(prefix="/api/v1", tags=["seller-lead"])

BFF_SECRET = os.getenv("SMARTBUY_BFF_SECRET")

Ownership = Literal["acquisto", "successione", "donazione"]
Contract = Literal["vendita", "affitto"]


class SellerLeadAnswers(BaseModel):
    address: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=100)
    contract: Contract | None = None
    typology: str | None = None
    is_condominium: bool | None = None
    ownership_origin: Ownership | None = None
    is_rented: bool | None = None
    documents_ready: list[str] = Field(default_factory=list)
    surface_m2: float | None = Field(default=None, gt=0, le=5000)
    floor: int | None = Field(default=None, ge=-2, le=60)
    elevator: bool | None = None
    condition: str | None = None


class SellerLeadReportRequest(SellerLeadAnswers):
    email: EmailStr


def require_bff(
    x_smartbuy_bff_token: str | None = Header(default=None),
) -> None:
    if not BFF_SECRET:
        raise HTTPException(
            status_code=503,
            detail="Seller lead service not configured",
        )

    if not x_smartbuy_bff_token or not secrets.compare_digest(
        x_smartbuy_bff_token,
        BFF_SECRET,
    ):
        raise HTTPException(
            status_code=403,
            detail="Forbidden",
        )


def _locate(
    answers: SellerLeadAnswers,
) -> tuple[tuple[float, float] | None, dict[str, Any] | None]:
    if not answers.address or not answers.city:
        return None, None

    location = resolve_location(answers.address, answers.city)

    if not location:
        return None, None

    return location, market_snapshot(supabase, *location)


@router.post("/seller-lead/preview")
def seller_lead_preview(
    answers: SellerLeadAnswers,
    x_smartbuy_bff_token: str | None = Header(default=None),
):
    """Return information derived from the quiz answers gathered so far.

    This endpoint is stateless and does not persist a seller lead.
    """

    require_bff(x_smartbuy_bff_token)

    location, zone = _locate(answers)

    reveal: dict[str, Any] = {}

    if answers.address and answers.city and zone is None:
        reveal["location_error"] = (
            "Indirizzo non riconosciuto in questo comune: controlla la scrittura."
        )

    if zone:
        reveal["zone_price_range"] = zone_price_range(zone)
        reveal["territory"] = territory_snapshot(supabase, zone)

        if location:
            reveal["proximity"] = proximity_snapshot(*location)

        if answers.typology:
            reveal["typology_price_range"] = typology_price_range(
                zone,
                answers.typology,
                answers.condition,
            )

    reveal["complexity"] = complexity_factors(
        answers.model_dump()
    )

    return reveal


@router.post("/seller-lead/report")
def seller_lead_report(
    request: SellerLeadReportRequest,
    x_smartbuy_bff_token: str | None = Header(default=None),
):
    """Generate the final seller report and persist the lead."""

    require_bff(x_smartbuy_bff_token)

    location, zone = _locate(request)

    if not zone:
        raise HTTPException(
            status_code=400,
            detail=(
                "Indirizzo non riconosciuto: torna al primo passo "
                "e controllalo."
            ),
        )

    estimate = full_estimate(
        city=request.city,
        typology_key=request.typology,
        contract=request.contract,
        condition=request.condition,
        floor=request.floor,
        elevator=request.elevator,
        surface_m2=request.surface_m2,
        zone=zone,
    )

    proximity = (
        proximity_snapshot(*location)
        if location
        else None
    )

    complexity = complexity_factors(
        request.model_dump()
    )

    answers_dict = request.model_dump(
        exclude={"email"}
    )

    report = compose_seller_report(
        answers=answers_dict,
        estimate=estimate,
        complexity=complexity,
        proximity=proximity,
    )

    row = {
        "email": str(request.email),
        "address": request.address,
        "city": request.city,
        "answers": answers_dict,
        "estimate": estimate,
        "complexity": complexity,
        "proximity": proximity,
        "report": report,
    }

    try:
        supabase.table("seller_leads").insert(row).execute()
    except Exception:
        # The report should still be returned even if lead persistence fails.
        pass

    return {
        "estimate": estimate,
        "complexity": complexity,
        "proximity": proximity,
        "report": report,
    }
