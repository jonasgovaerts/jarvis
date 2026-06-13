from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.api.deps import db_session, require_token
from gateway.chat.service import handle_message, name_session
from gateway.state import state
from jarvis_core.db import ChatMessage, ChatSession
from jarvis_core.dto import ChatMessage as ChatMessageDTO
from jarvis_core.dto import ChatSession as ChatSessionDTO
from jarvis_core.events import ChatRequestCreated

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", dependencies=[Depends(require_token)])


class SessionCreate(BaseModel):
    title: str = "New conversation"


class SessionUpdate(BaseModel):
    title: str


class MessageCreate(BaseModel):
    content: str


def _session_dto(s: ChatSession) -> ChatSessionDTO:
    return ChatSessionDTO(id=s.id, title=s.title, created_at=s.created_at)


def _message_dto(m: ChatMessage) -> ChatMessageDTO:
    return ChatMessageDTO(
        id=m.id,
        session_id=m.session_id,
        role=m.role,
        content=m.content,
        workflow_name=m.workflow_name,
        created_at=m.created_at,
    )


@router.get("/sessions")
async def list_sessions(session: AsyncSession = Depends(db_session)) -> list[ChatSessionDTO]:
    rows = await session.execute(
        select(ChatSession).order_by(ChatSession.created_at.desc()).limit(50)
    )
    return [_session_dto(s) for s in rows.scalars()]


@router.post("/sessions")
async def create_session(
    body: SessionCreate, session: AsyncSession = Depends(db_session)
) -> ChatSessionDTO:
    chat_session = ChatSession(title=body.title)
    session.add(chat_session)
    await session.commit()
    return _session_dto(chat_session)


@router.patch("/sessions/{session_id}")
async def patch_session(
    session_id: str, body: SessionUpdate, session: AsyncSession = Depends(db_session)
) -> ChatSessionDTO:
    chat_session = await session.get(ChatSession, session_id)
    if chat_session is None:
        raise HTTPException(status_code=404, detail="session not found")
    chat_session.title = body.title
    await session.commit()
    return _session_dto(chat_session)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, session: AsyncSession = Depends(db_session)):
    # Delete messages explicitly: the live chat_messages table predates the
    # ondelete=CASCADE on the FK (create_all never ALTERs), and there is no
    # ORM relationship to cascade through, so deleting the session alone would
    # hit a foreign-key violation.
    await session.execute(delete(ChatMessage).where(ChatMessage.session_id == session_id))
    await session.execute(delete(ChatSession).where(ChatSession.id == session_id))
    await session.commit()


@router.get("/sessions/{session_id}/messages")
async def list_messages(
    session_id: str, session: AsyncSession = Depends(db_session)
) -> list[ChatMessageDTO]:
    rows = await session.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .limit(200)
    )
    return [_message_dto(m) for m in rows.scalars()]


@router.post("/sessions/{session_id}/messages")
async def post_message(
    session_id: str, body: MessageCreate, session: AsyncSession = Depends(db_session)
) -> ChatMessageDTO:
    chat_session = await session.get(ChatSession, session_id)
    if chat_session is None:
        raise HTTPException(status_code=404, detail="session not found")

    user_msg = ChatMessage(session_id=session_id, role="user", content=body.content)
    session.add(user_msg)
    await session.commit()

    rows = await session.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )
    history_records = list(rows.scalars())
    history = [{"role": m.role, "content": m.content} for m in history_records]

    try:
        outcome = await handle_message(history[:-1], body.content, session_id)
        reply, workflow_name = outcome.reply, outcome.workflow_name
    except Exception as exc:  # noqa: BLE001 - surface the failure in-channel
        log.exception("chat handling failed")
        reply, workflow_name = f"Something went wrong handling that: {exc}", ""

    if chat_session.title == "New conversation" and len(history_records) < 2:
        try:
            new_title = await name_session(history)
            chat_session.title = new_title
        except Exception:
            log.exception("session naming failed")

    assistant_msg = ChatMessage(
        session_id=session_id, role="assistant", content=reply, workflow_name=workflow_name
    )
    session.add(assistant_msg)
    await session.commit()

    if workflow_name and state.js is not None:
        from jarvis_core import bus

        await bus.publish(
            state.js,
            "jarvis.chat.request.created",
            ChatRequestCreated(
                session_id=session_id,
                workflow_name=workflow_name,
                repository="",
                title=body.content[:120],
            ),
            source="gateway",
            msg_id=f"chat-created:{workflow_name}",
        )

    return _message_dto(assistant_msg)
