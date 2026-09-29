"""Real feedback correction E2E smoke test for SmartBuy.

Requires main_api running locally and .env with:
SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, SUPABASE_SECRET_KEY.
No OpenAI call is made.
"""
from __future__ import annotations

import os
import secrets
import uuid

import httpx
from dotenv import load_dotenv
from supabase import create_client

load_dotenv(".env")

BASE = os.getenv("SMARTBUY_API_URL", "http://127.0.0.1:8000").rstrip("/")
SUPABASE_URL = os.environ["SUPABASE_URL"]
PUBLIC_KEY = os.environ["SUPABASE_PUBLISHABLE_KEY"]
SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]

admin = create_client(SUPABASE_URL, SECRET_KEY)

user_id: str | None = None
property_id: int | None = None
token: str | None = None
scoped = None
failures: list[str] = []


def check(condition: bool, label: str) -> None:
    marker = "PASS" if condition else "FAIL"
    print(f"[{marker}] {label}")
    if not condition:
        failures.append(label)


def ref(category: str) -> dict:
    return {
        "comune": "Bologna",
        "foglio": "123",
        "particella": "456",
        "subalterno": "7",
        "categoria": category,
    }


try:
    print("1. Creo utente test temporaneo...")
    email = f"smartbuy-feedback-{uuid.uuid4().hex[:10]}@example.com"
    password = secrets.token_urlsafe(24) + "Aa1!"
    created = admin.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True}
    )
    user_id = str(created.user.id)

    scoped = create_client(SUPABASE_URL, PUBLIC_KEY)
    signed = scoped.auth.sign_in_with_password({"email": email, "password": password})
    token = signed.session.access_token
    headers = {"Authorization": f"Bearer {token}"}
    print("   OK")

    with httpx.Client(timeout=60.0) as http:
        print("\n2. Creo immobile via API...")
        response = http.post(
            f"{BASE}/api/v1/properties",
            headers=headers,
            json={
                "address": "Via Feedback Test 1",
                "city": "Bologna",
                "typology": "appartamento",
                "contract": "vendita",
            },
        )
        check(response.status_code == 201, "Immobile creato")
        if response.status_code != 201:
            print(response.text)
            raise SystemExit(1)
        property_id = int(response.json()["id"])

        print("\n3. Creo due documenti/facts in conflitto A/3 vs A/2...")
        doc_ids = []
        fact_ids = {}
        for category in ("A/3", "A/2"):
            doc = (
                scoped.table("documents")
                .insert(
                    {
                        "fascicolo_id": str(property_id),
                        "agente_id": user_id,
                        "file_name": f"visura_{category.replace('/', '').lower()}.pdf",
                        "document_type": "visura_catastale",
                        "processing_status": "completed",
                        "source_type": "account_upload",
                        "extracted_fields": {"riferimento": ref(category)},
                        "extraction_confidence": 0.99,
                        "confidence_score": 0.99,
                    }
                )
                .execute()
                .data[0]
            )
            doc_id = int(doc["id"])
            doc_ids.append(doc_id)

            (
                scoped.table("document_analyses")
                .insert(
                    {
                        "property_id": property_id,
                        "document_id": str(doc_id),
                        "document_name": doc["file_name"],
                        "document_type": "visura_catastale",
                        "analysis_status": "completed",
                        "confidence_score": 0.99,
                        "extracted_data": doc["extracted_fields"],
                        "warnings": [],
                    }
                )
                .execute()
            )

            fact = (
                scoped.table("property_facts")
                .insert(
                    {
                        "property_id": property_id,
                        "fact_name": "riferimento",
                        "fact_value": {"value": ref(category)},
                        "source_type": "document",
                        "source_document_id": doc_id,
                        "confidence_score": 0.99,
                        "verification_status": "unverified",
                    }
                )
                .execute()
                .data[0]
            )
            fact_ids[category] = str(fact["id"])
        print("   OK")

        print("\n4. Verifico il conflitto iniziale...")
        before_cross = http.get(
            f"{BASE}/api/v1/properties/{property_id}/cross-validation",
            headers=headers,
        )
        before_intel = http.get(
            f"{BASE}/api/v1/properties/{property_id}/intelligence",
            headers=headers,
        )
        check(before_cross.status_code == 200, "Cross-validation iniziale disponibile")
        check(before_intel.status_code == 200, "Intelligence iniziale disponibile")

        cross_payload = before_cross.json()
        intel_payload = before_intel.json()
        before_summary = cross_payload.get("summary", {})
        category_before = [
            f for f in cross_payload.get("findings", [])
            if f.get("field") == "catasto.categoria"
        ]

        check(before_summary.get("conflicts") == 1, "Prima del feedback esiste 1 conflitto")
        check(before_summary.get("blocking") == 1, "Prima del feedback il conflitto è blocking")
        check(
            category_before and category_before[0].get("status") == "conflict",
            "Prima del feedback catasto.categoria è conflict",
        )
        check(intel_payload.get("summary", {}).get("open_risks") == 1, "Prima del feedback intelligence ha 1 rischio aperto")

        target = next(
            (
                fact for fact in intel_payload.get("facts", [])
                if str(fact.get("id")) == fact_ids["A/2"]
            ),
            None,
        )
        check(target is not None, "Il fact A/2 è esposto dall'intelligence con metadata feedback")
        if target is None:
            raise SystemExit(1)

        feedback_meta = target["feedback"]

        print("\n5. Correggo A/2 in A/3 tramite endpoint feedback reale...")
        feedback = http.post(
            f"{BASE}/api/v1/feedback",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "property_id": property_id,
                "target_type": "FACT",
                "target_id": fact_ids["A/2"],
                "expected_version": feedback_meta["expected_version"],
                "action": "CORRECT",
                "original_payload": feedback_meta["original_payload"],
                "corrected_payload": {
                    "field": "riferimento",
                    "value": ref("A/3"),
                },
                "failure_stage": "EXTRACTION",
                "component_versions": {
                    "feedback_e2e": "1.0",
                    "cross_validation": "3.1",
                },
            },
        )
        check(feedback.status_code == 200, "Feedback CORRECT accettato")
        if feedback.status_code != 200:
            print(feedback.text)
            raise SystemExit(1)
        check(feedback.json().get("status") == "accepted", "Ricevuta feedback = accepted")

        persisted = (
            scoped.table("property_facts")
            .select("id,verification_status,verified_value")
            .eq("id", fact_ids["A/2"])
            .limit(1)
            .execute()
            .data[0]
        )
        check(persisted.get("verification_status") == "corrected", "Il fact è marcato corrected")
        check(
            (persisted.get("verified_value") or {}).get("value", {}).get("categoria") == "A/3",
            "verified_value contiene la categoria corretta A/3",
        )

        jobs = (
            scoped.table("smartbuy_recalculation_jobs")
            .select("stages,status")
            .eq("property_id", property_id)
            .execute()
            .data
            or []
        )
        check(bool(jobs), "È stato registrato il job di ricalcolo")
        if jobs:
            stages = jobs[-1].get("stages") or []
            check("cross_validation" in stages and "risk" in stages, "Il job richiede cross-validation e risk recalculation")

        print("\n6. Ricalcolo tramite gli endpoint reali...")
        after_cross = http.get(
            f"{BASE}/api/v1/properties/{property_id}/cross-validation",
            headers=headers,
        )
        after_intel = http.get(
            f"{BASE}/api/v1/properties/{property_id}/intelligence",
            headers=headers,
        )
        check(after_cross.status_code == 200, "Cross-validation dopo feedback disponibile")
        check(after_intel.status_code == 200, "Intelligence dopo feedback disponibile")

        after_cross_payload = after_cross.json()
        after_intel_payload = after_intel.json()
        after_summary = after_cross_payload.get("summary", {})
        category_after = [
            f for f in after_cross_payload.get("findings", [])
            if f.get("field") == "catasto.categoria"
        ]

        check(after_summary.get("conflicts") == 0, "Dopo il feedback non restano conflitti")
        check(after_summary.get("blocking") == 0, "Dopo il feedback non restano blocker")
        check(
            category_after and category_after[0].get("status") in {"consistent", "compatible"},
            "Dopo il feedback catasto.categoria è coerente",
        )
        check(
            after_intel_payload.get("summary", {}).get("open_risks") == 0,
            "Dopo il feedback intelligence non ha rischi di conflitto aperti",
        )
        check(
            not any(r.get("category") == "factual_discrepancy" for r in after_intel_payload.get("risks", [])),
            "Il rischio factual_discrepancy è scomparso",
        )

        corrected_fact = next(
            (
                fact for fact in after_intel_payload.get("facts", [])
                if str(fact.get("id")) == fact_ids["A/2"]
            ),
            None,
        )
        check(corrected_fact is not None and corrected_fact.get("status") == "corrected", "La UI intelligence vedrebbe il fact come corrected")

finally:
    if property_id is not None and token:
        try:
            with httpx.Client(timeout=60.0) as http:
                cleanup = http.delete(
                    f"{BASE}/api/v1/properties/{property_id}",
                    headers={"Authorization": f"Bearer {token}"},
                )
                print(f"\nPulizia property: HTTP {cleanup.status_code}")
        except Exception as exc:
            print("Pulizia property non riuscita:", type(exc).__name__)

    if user_id:
        try:
            admin.auth.admin.delete_user(user_id)
            print("Pulizia utente test: OK")
        except Exception as exc:
            print("Pulizia utente non riuscita:", type(exc).__name__)

if failures:
    print("\n❌ FEEDBACK E2E NON SUPERATO")
    for item in failures:
        print(" -", item)
    raise SystemExit(1)

print("\n✅ FEEDBACK E2E SUPERATO")
