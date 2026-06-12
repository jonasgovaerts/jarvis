from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


# --- gateway-owned ------------------------------------------------------------


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(200), default="New conversation")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    workflow_name: Mapped[str] = mapped_column(String(63), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class EmailDraft(Base):
    """Gateway projection of workspace draft events + the approval state."""

    __tablename__ = "email_drafts"

    task_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    gmail_draft_id: Mapped[str] = mapped_column(String(64), default="")
    thread_id: Mapped[str] = mapped_column(String(64), default="")
    subject: Mapped[str] = mapped_column(String(500), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|approved|discarded
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class WorkflowEvent(Base):
    """Append-only event history feeding the detail page's phase timeline."""

    __tablename__ = "workflow_events"
    __table_args__ = (Index("ix_workflow_events_name_time", "workflow_name", "time"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workflow_name: Mapped[str] = mapped_column(String(63))
    subject: Mapped[str] = mapped_column(String(100))
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    data: Mapped[dict] = mapped_column(JSON, default=dict)


# --- notifier-owned -----------------------------------------------------------


class NotificationLog(Base):
    """Idempotency + audit for notification delivery (event_id × channel)."""

    __tablename__ = "notification_log"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    channel: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|sent|failed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# --- workspace-owned ----------------------------------------------------------


class GmailSyncState(Base):
    __tablename__ = "gmail_sync_state"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    email_address: Mapped[str] = mapped_column(String(200), default="")
    last_history_id: Mapped[str] = mapped_column(String(32), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class Email(Base):
    __tablename__ = "emails"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    gmail_message_id: Mapped[str] = mapped_column(String(64), unique=True)
    thread_id: Mapped[str] = mapped_column(String(64), default="")
    subject: Mapped[str] = mapped_column(String(500), default="")
    from_addr: Mapped[str] = mapped_column(String(320), default="")
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    category: Mapped[str] = mapped_column(
        String(20), default=""
    )  # task|informational|newsletter|spam_ish
    confidence: Mapped[str] = mapped_column(String(8), default="")
    status: Mapped[str] = mapped_column(
        String(16), default="pending"
    )  # pending|classified|done|failed
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Task(Base):
    """Created by workspace from task emails; gateway updates status only."""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email_id: Mapped[str | None] = mapped_column(ForeignKey("emails.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(16), default="normal")
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)  # open|done|snoozed
    needs_reply: Mapped[bool] = mapped_column(default=True)
    gmail_message_id: Mapped[str] = mapped_column(String(64), default="")
    gmail_draft_id: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
