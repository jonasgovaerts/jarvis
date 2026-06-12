"""Shared SQLAlchemy models and engine helpers.

One database, per-service table ownership (workspace owns emails/tasks/
gmail_sync_state, gateway owns chat/drafts/workflow_events, notifier owns
notification_log). The single deliberate exception: `tasks` is created by
workspace and status-updated by the gateway.
"""

from jarvis_core.db.engine import create_engine_and_factory, init_models
from jarvis_core.db.models import (
    Base,
    ChatMessage,
    ChatSession,
    Email,
    EmailDraft,
    GmailSyncState,
    NotificationLog,
    Task,
    WorkflowEvent,
)

__all__ = [
    "Base",
    "ChatMessage",
    "ChatSession",
    "Email",
    "EmailDraft",
    "GmailSyncState",
    "NotificationLog",
    "Task",
    "WorkflowEvent",
    "create_engine_and_factory",
    "init_models",
]
