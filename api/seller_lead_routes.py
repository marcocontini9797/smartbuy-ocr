"""Public, unauthenticated seller/buyer lead-generation quiz.

Requests are accepted only through the SmartBuy web BFF, authenticated
with SMARTBUY_BFF_SECRET.

Public seller-lead endpoints are protected by persistent Supabase rate
limits before any expensive geocoding, market-data or LLM work is done.
IP addresses and emails are never stored in the rate-limit table: only
keyed SHA-256 hashes are persisted.
"""

from __future__ import annotations

import hashlib
import hmac
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


def _subject_hash(value: str) -> str:
    """Return a stable keyed hash without persisting the raw subject."""

    if not BFF_SECRET:
        raise HTTPException(
            status_code=503,
            detail="Seller lead service not configured",
        )

    return hmac.new(
        BFF_SECRET.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _consume_rate_limit(
    *,
    scope: str,
    subject: str,
    window_seconds: int,
    limit: int,
) -> None:
    try:
        response = supabase.rpc(
            "smartbuy_consume_public_rate_limit",
            {
                "p_scope": scope,
                "p_subject_hash": _subject_hash(subject),
                "p_window_seconds": window_seconds,
                "p_limit": limit,
            },
        ).execute()

        result = response.data

        if isinstance(result, list):
            result = result[0] if result else None

        if not isinstance(result, dict):
            raise ValueError("Unexpected rate-limit response")

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Rate limit service unavailable",
        ) from exc

    if not bool(result.get("allowed")):
        try:
            retry_after = max(
                1,
                int(result.get("retry_after") or window_seconds),
            )
        except (TypeError, ValueError):
            retry_after = window_seconds

        raise HTTPException(
            status_code=429,
            detail="Troppe richieste. Riprova più tardi.",
            headers={
                "Retry-After": str(retry_after),
            },
        )


def _enforce_preview_limits(client_ip: str) -> None:
    # Normal quiz navigation can call preview several times.
    _consume_rate_limit(
        scope="seller_preview_ip_10m",
        subject=client_ip,
        window_seconds=600,
        limit=30,
    )

    _consume_rate_limit(
        scope="seller_preview_ip_day",
        subject=client_ip,
        window_seconds=86400,
        limit=200,
    )


def _enforce_report_limits(
    client_ip: str,
    email: str,
) -> None:
    # Report generation is more expensive because it can invoke the LLM.
    _consume_rate_limit(
        scope="seller_report_ip_hour",
        subject=client_ip,
        window_seconds=3600,
        limit=5,
    )

    _consume_rate_limit(
        scope="seller_report_ip_day",
        subject=client_ip,
        window_seconds=86400,
        limit=10,
    )

    _consume_rate_limit(
        scope="seller_report_email_day",
        subject=email.strip().lower(),
        window_seconds=86400,
        limit=3,
    )

    # Emergency cost ceiling across the whole public report funnel.
    _consume_rate_limit(
        scope="seller_report_global_day",
        subject="smartbuy-public-report-global",
        window_seconds=86400,
        limit=100,
    )


def _client_ip(
    x_smartbuy_client_ip: str | None,
) -> str:
    value = (x_smartbuy_client_ip or "unknown").strip()

    if not value:
        return "unknown"

    return value[:128]


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
    x_smartbuy_client_ip: str | None = Header(default=None),
):
    """Return information derived from quiz answers gathered so far."""

    require_bff(x_smartbuy_bff_token)

    client_ip = _client_ip(x_smartbuy_client_ip)

    # Important: rate-limit before geocoding or other external work.
    _enforce_preview_limits(client_ip)

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
    x_smartbuy_client_ip: str | None = Header(default=None),
):
    """Generate the final seller report and persist the lead."""

    require_bff(x_smartbuy_bff_token)

    client_ip = _client_ip(x_smartbuy_client_ip)

    # Important: all rate limits run before geocoding and LLM generation.
    _enforce_report_limits(
        client_ip,
        str(request.email),
    )

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
        # The report should still be returned if lead persistence alone fails.
        pass

    return {
        "estimate": estimate,
        "complexity": complexity,
        "proximity": proximity,
        "report": report,
    }
