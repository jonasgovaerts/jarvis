from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.api.deps import db_session, require_token
from gateway.config import settings
from gateway.k8s import ops
from gateway.state import state
from jarvis_core.db import WorkflowEvent
from jarvis_core.dto import BoardItem
from jarvis_core.dto import WorkflowEvent as WorkflowEventDTO

router = APIRouter(prefix="/api/workflows", dependencies=[Depends(require_token)])


class WorkflowDetail(BaseModel):
    item: BoardItem
    spec: dict
    status: dict
    history: list[WorkflowEventDTO]


class ActionRequest(BaseModel):
    action: Literal["approve", "retry", "cancel"]


@router.get("")
async def list_workflows(phase: str | None = None, repo: str | None = None) -> list[BoardItem]:
    return state.cache.list(phase=phase, repo=repo)


@router.get("/{name}")
async def get_workflow(name: str, session: AsyncSession = Depends(db_session)) -> WorkflowDetail:
    raw = state.cache.get_raw(name)
    items = {i.name: i for i in state.cache.list()}
    if name not in items:
        raise HTTPException(status_code=404, detail=f"workflow {name} not found")

    rows = await session.execute(
        select(WorkflowEvent)
        .where(WorkflowEvent.workflow_name == name)
        .order_by(WorkflowEvent.time.asc())
        .limit(200)
    )
    history = [
        WorkflowEventDTO(subject=row.subject, time=row.time, data=row.data)
        for row in rows.scalars()
    ]
    return WorkflowDetail(
        item=items[name],
        spec=(raw or {}).get("spec", {}),
        status=(raw or {}).get("status", {}),
        history=history,
    )


@router.post("/{name}/actions")
async def request_action(name: str, body: ActionRequest) -> dict:
    if state.cache.get_raw(name) is None and not settings().fake_k8s:
        raise HTTPException(status_code=404, detail=f"workflow {name} not found")
    if settings().fake_k8s:
        return {"status": "accepted", "action": body.action, "note": "fixture mode"}
    await ops.request_action(settings().workitem_namespace, name, body.action)
    return {"status": "accepted", "action": body.action}


@router.delete("/{name}", status_code=204)
async def delete_workflow(name: str, session: AsyncSession = Depends(db_session)):
    if state.cache.get_raw(name) is None and not settings().fake_k8s:
        raise HTTPException(status_code=404, detail=f"workflow {name} not found")
    if not settings().fake_k8s:
        await ops.delete_workitem(settings().workitem_namespace, name)

    await session.execute(delete(WorkflowEvent).where(WorkflowEvent.workflow_name == name))
    await session.commit()
