"""Pending requests an agent has to send by hand: cadastral, condo, notary.

Surfaces the `tasks` table (created for a standalone prototype that never
shipped, see document_engine/agent_tasks.py) inside the real workspace.
Ownership is enforced the same way as every other property-scoped route:
get_property() 404s before any tasks/ query runs, so a caller can only ever
see tasks for a property they own, independent of RLS on the tasks table.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.property_routes import get_property
from api.session import user_client
from document_engine.agent_tasks import GENERATABLE_TASK_TYPES, TASK_LABELS, generate_task_content

router = APIRouter(prefix="/api/v1", tags=["agent-tasks"])

TaskStatus = Literal["pending", "in_progress", "completed", "cancelled"]


class TaskUpdate(BaseModel):
    status: TaskStatus | None = None
    notes: str | None = Field(default=None, max_length=2000)


def _tasks(client, property_id: int) -> list[dict]:
    try:
        response = (
            client.table("tasks").select("*").eq("property_id", property_id)
            .order("created_at", desc=True).execute()
        )
        return response.data or []
    except Exception as exc:
        raise HTTPException(502, "Servizio richieste non raggiungibile") from exc


@router.get("/properties/{property_id}/tasks")
def list_tasks(property_id: int, client=Depends(user_client)):
    get_property(property_id, client)
    tasks = _tasks(client, property_id)
    return {"tasks": tasks, "labels": TASK_LABELS}


@router.post("/properties/{property_id}/tasks/generate", status_code=201)
def generate_tasks(property_id: int, client=Depends(user_client)):
    """Create the missing draft requests for this property (idempotent: a
    task_type already open - pending or in_progress - is left alone)."""
    property_record = get_property(property_id, client)
    existing = _tasks(client, property_id)
    open_types = {t["task_type"] for t in existing if t.get("status") in {"pending", "in_progress"}}
    to_create = [t for t in GENERATABLE_TASK_TYPES if t not in open_types]
    if to_create:
        rows = [
            {"property_id": property_id, "task_type": task_type,
             "generated_content": generate_task_content(task_type, property_record)}
            for task_type in to_create
        ]
        try:
            client.table("tasks").insert(rows).execute()
        except Exception as exc:
            raise HTTPException(502, "Impossibile generare le richieste") from exc
    return {"tasks": _tasks(client, property_id), "labels": TASK_LABELS}


@router.patch("/properties/{property_id}/tasks/{task_id}")
def update_task(property_id: int, task_id: str, payload: TaskUpdate, client=Depends(user_client)):
    get_property(property_id, client)
    changes = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not changes:
        raise HTTPException(400, "Nessuna modifica indicata")
    try:
        response = (
            client.table("tasks").update(changes)
            .eq("id", task_id).eq("property_id", property_id).execute()
        )
    except Exception as exc:
        raise HTTPException(502, "Impossibile aggiornare la richiesta") from exc
    if not response.data:
        raise HTTPException(404, "Richiesta non trovata")
    return response.data[0]
