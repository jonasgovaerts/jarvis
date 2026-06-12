from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.api.deps import db_session, require_token
from gateway.state import state
from jarvis_core.db import EmailDraft
from jarvis_core.dto import DraftEmail
from jarvis_core.events import EmailDraftApproved

router = APIRouter(prefix="/api/drafts", dependencies=[Depends(require_token)])


class DraftAction(BaseModel):
    action: Literal["approve", "discard"]


def _to_dto(draft: EmailDraft) -> DraftEmail:
    return DraftEmail(
        task_id=draft.task_id,
        gmail_draft_id=draft.gmail_draft_id,
        thread_id=draft.thread_id,
        subject=draft.subject,
        summary=draft.summary,
        status=draft.status,
        created_at=draft.created_at,
    )


@router.get("")
async def list_drafts(session: AsyncSession = Depends(db_session)) -> list[DraftEmail]:
    rows = await session.execute(
        select(EmailDraft).order_by(EmailDraft.created_at.desc()).limit(100)
    )
    return [_to_dto(d) for d in rows.scalars()]


@router.post("/{task_id}/actions")
async def draft_action(
    task_id: str, body: DraftAction, session: AsyncSession = Depends(db_session)
) -> DraftEmail:
    draft = await session.get(EmailDraft, task_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="draft not found")
    draft.status = "approved" if body.action == "approve" else "discarded"
    await session.commit()

    if body.action == "approve" and state.js is not None:
        from jarvis_core import bus

        await bus.publish(
            state.js,
            "jarvis.email.draft.approved",
            EmailDraftApproved(task_id=task_id, gmail_draft_id=draft.gmail_draft_id),
            source="gateway",
            msg_id=f"draft-approved:{task_id}",
        )
    return _to_dto(draft)
