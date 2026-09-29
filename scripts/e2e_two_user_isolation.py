"""Real two-user isolation smoke test for SmartBuy.

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

users: list[str] = []
property_id: int | None = None
document_id: int | None = None
token_a: str | None = None
client_a = None
failures: list[str] = []


def check(condition: bool, label: str) -> None:
    marker = "PASS" if condition else "FAIL"
    print(f"[{marker}] {label}")
    if not condition:
        failures.append(label)


def create_test_user(label: str):
    email = f"smartbuy-isolation-{label}-{uuid.uuid4().hex[:10]}@example.com"
    password = secrets.token_urlsafe(24) + "Aa1!"
    created = admin.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True}
    )
    user_id = str(created.user.id)
    users.append(user_id)

    scoped = create_client(SUPABASE_URL, PUBLIC_KEY)
    signed = scoped.auth.sign_in_with_password({"email": email, "password": password})
    return user_id, scoped, signed.session.access_token


try:
    print("1. Creo due agenti temporanei A e B...")
    user_a, client_a, token_a = create_test_user("a")
    user_b, client_b, token_b = create_test_user("b")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}
    print("   OK")

    with httpx.Client(timeout=60.0) as http:
        print("\n2. A crea il proprio immobile via API...")
        response = http.post(
            f"{BASE}/api/v1/properties",
            headers=headers_a,
            json={
                "address": "Via Test Isolamento 1",
                "city": "Bologna",
                "typology": "appartamento",
                "contract": "vendita",
            },
        )
        check(response.status_code == 201, "A può creare il proprio immobile")
        if response.status_code != 201:
            print(response.text)
            raise SystemExit(1)
        property_id = int(response.json()["id"])

        print("\n3. A crea un documento minimo e lo collega alla property...")
        inserted = (
            client_a.table("documents")
            .insert(
                {
                    "fascicolo_id": str(property_id),
                    "agente_id": user_a,
                    "file_name": "isolamento-test.pdf",
                    "document_type": "visura_catastale",
                    "processing_status": "completed",
                    "source_type": "account_upload",
                    "extracted_fields": {
                        "riferimento": {
                            "comune": "Bologna",
                            "foglio": "999",
                            "particella": "888",
                            "subalterno": "7",
                            "categoria": "A/3",
                        }
                    },
                    "extraction_confidence": 0.99,
                    "confidence_score": 0.99,
                }
            )
            .execute()
        )
        document_id = int(inserted.data[0]["id"])

        (
            client_a.table("document_analyses")
            .insert(
                {
                    "property_id": property_id,
                    "document_id": str(document_id),
                    "document_name": "isolamento-test.pdf",
                    "document_type": "visura_catastale",
                    "analysis_status": "completed",
                    "confidence_score": 0.99,
                    "extracted_data": inserted.data[0]["extracted_fields"],
                    "warnings": [],
                }
            )
            .execute()
        )

        storage_path = f"{user_a}/{property_id}/isolamento-test.pdf"
        client_a.storage.from_("smartbuy-documents").upload(
            storage_path,
            b"%PDF-1.4\n% SmartBuy two-user isolation test\n",
            file_options={"content-type": "application/pdf", "upsert": "false"},
        )
        (
            client_a.table("documents")
            .update({"storage_path": storage_path})
            .eq("id", document_id)
            .execute()
        )
        print("   OK")

        print("\n4. Controllo accesso dell'agente A...")
        a_property = http.get(f"{BASE}/api/v1/properties/{property_id}", headers=headers_a)
        a_workspace = http.get(f"{BASE}/api/v1/properties/{property_id}/workspace", headers=headers_a)
        a_cross = http.get(f"{BASE}/api/v1/properties/{property_id}/cross-validation", headers=headers_a)
        a_intel = http.get(f"{BASE}/api/v1/properties/{property_id}/intelligence", headers=headers_a)
        a_file = http.get(
            f"{BASE}/api/v1/properties/{property_id}/documents/{document_id}/file",
            headers=headers_a,
        )

        check(a_property.status_code == 200, "A vede la propria property")
        check(a_workspace.status_code == 200, "A apre il proprio workspace")
        check(a_cross.status_code == 200, "A accede alla propria cross-validation")
        check(a_intel.status_code == 200, "A accede alla propria intelligence")
        check(a_file.status_code == 200, "A può ottenere il link firmato del proprio originale")

        if a_workspace.status_code == 200:
            workspace_docs = a_workspace.json().get("documents", [])
            check(
                any(str(row.get("id")) == str(document_id) for row in workspace_docs),
                "Il documento di A compare nel workspace di A",
            )

        print("\n5. B prova ad accedere ai dati di A...")
        b_list = http.get(f"{BASE}/api/v1/properties", headers=headers_b)
        b_property = http.get(f"{BASE}/api/v1/properties/{property_id}", headers=headers_b)
        b_workspace = http.get(f"{BASE}/api/v1/properties/{property_id}/workspace", headers=headers_b)
        b_cross = http.get(f"{BASE}/api/v1/properties/{property_id}/cross-validation", headers=headers_b)
        b_intel = http.get(f"{BASE}/api/v1/properties/{property_id}/intelligence", headers=headers_b)
        b_file = http.get(
            f"{BASE}/api/v1/properties/{property_id}/documents/{document_id}/file",
            headers=headers_b,
        )

        listed_ids = {
            str(row.get("id"))
            for row in (b_list.json() if b_list.status_code == 200 else [])
        }
        check(b_list.status_code == 200 and str(property_id) not in listed_ids, "B non vede la property di A nella lista")
        check(b_property.status_code == 404, "B non può aprire la property di A")
        check(b_workspace.status_code == 404, "B non può aprire il workspace di A")
        check(b_cross.status_code == 404, "B non può eseguire cross-validation sulla property di A")
        check(b_intel.status_code == 404, "B non può leggere intelligence della property di A")
        check(b_file.status_code == 404, "B non può ottenere il file originale di A via API")

        direct_docs_b = (
            client_b.table("documents")
            .select("id,file_name,storage_path")
            .eq("id", document_id)
            .execute()
            .data
            or []
        )
        check(direct_docs_b == [], "RLS nasconde direttamente a B la riga documents di A")

        storage_denied = False
        try:
            client_b.storage.from_("smartbuy-documents").create_signed_url(storage_path, 60)
        except Exception:
            storage_denied = True
        check(storage_denied, "Storage RLS impedisce a B di firmare il file di A")

        cross_insert_denied = False
        try:
            client_b.table("document_analyses").insert(
                {
                    "property_id": property_id,
                    "document_id": str(document_id),
                    "document_name": "tentativo-b.pdf",
                    "analysis_status": "completed",
                }
            ).execute()
        except Exception:
            cross_insert_denied = True
        check(cross_insert_denied, "B non può inserire analisi sulla property di A")

finally:
    if property_id is not None and token_a:
        try:
            with httpx.Client(timeout=60.0) as http:
                cleanup = http.delete(
                    f"{BASE}/api/v1/properties/{property_id}",
                    headers={"Authorization": f"Bearer {token_a}"},
                )
                print(f"\nPulizia property: HTTP {cleanup.status_code}")
        except Exception as exc:
            print("Pulizia property non riuscita:", type(exc).__name__)

    for user_id in users:
        try:
            admin.auth.admin.delete_user(user_id)
        except Exception as exc:
            print("Pulizia utente non riuscita:", user_id, type(exc).__name__)

    if users:
        print("Pulizia utenti test: completata")

if failures:
    print("\n❌ ISOLAMENTO DUE UTENTI NON SUPERATO")
    for item in failures:
        print(" -", item)
    raise SystemExit(1)

print("\n✅ ISOLAMENTO DUE UTENTI SUPERATO")
