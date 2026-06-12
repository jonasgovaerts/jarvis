from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.api.deps import db_session, require_token
from gateway.state import state
from jarvis_core.db import Task
from jarvis_core.dto import UserTask
from jarvis_core.events import TaskCompleted

router = APIRouter(prefix="/api/tasks", dependencies=[Depends(require_token)])


class TaskPatch(BaseModel):
    status: Literal["open", "done", "snoozed"]


def _to_dto(task: Task) -> UserTask:
    return UserTask(
        id=task.id,
        title=task.title,
        description=task.description,
        priority=task.priority,
        status=task.status,
        gmail_message_id=task.gmail_message_id,
        gmail_draft_id=task.gmail_draft_id,
        created_at=task.created_at,
    )


@router.get("")
async def list_tasks(
    status: str | None = None, session: AsyncSession = Depends(db_session)
) -> list[UserTask]:
    query = select(Task).order_by(Task.created_at.desc()).limit(200)
    if status:
        query = query.where(Task.status == status)
    rows = await session.execute(query)
    return [_to_dto(task) for task in rows.scalars()]


@router.patch("/{task_id}")
async def update_task(
    task_id: str, body: TaskPatch, session: AsyncSession = Depends(db_session)
) -> UserTask:
    task = await session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    task.status = body.status
    await session.commit()

    if body.status == "done" and state.js is not None:
        from jarvis_core import bus

        await bus.publish(
            state.js,
            "jarvis.task.completed",
            TaskCompleted(task_id=task_id),
            source="gateway",
            msg_id=f"task-completed:{task_id}",
        )
    return _to_dto(task)
