"""REST DTOs served by the gateway — exported to TS alongside the events.

These are read models for the frontend; Kubernetes CRs stay the source of truth
for workflow state and Postgres for tasks/chat. Wire format is camelCase.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from jarvis_core.events import AnalysisVerdict, SourceType, WorkItemPhase, _EventModel


class BoardItem(_EventModel):
    """One card on the kanban board — a WorkItem projected for the UI."""

    name: str
    repository: str
    title: str
    source_type: SourceType
    phase: WorkItemPhase
    message: str = ""
    verdict: AnalysisVerdict | None = None
    pr_url: str = ""
    failed: bool = False
    created_at: datetime
    updated_at: datetime | None = None


class WorkflowEvent(_EventModel):
    """One row of a workflow's phase history (gateway projection of NATS events)."""

    subject: str
    time: datetime
    data: dict = Field(default_factory=dict)


class UserTask(_EventModel):
    id: str
    title: str
    description: str = ""
    priority: str = "normal"
    status: str = "open"  # open | done | snoozed
    gmail_message_id: str = ""
    gmail_draft_id: str = ""
    created_at: datetime


class DraftEmail(_EventModel):
    task_id: str
    gmail_draft_id: str
    thread_id: str
    subject: str
    summary: str
    status: str = "pending"  # pending | approved | discarded
    created_at: datetime


class ChatMessage(_EventModel):
    id: str
    session_id: str
    role: str  # user | assistant
    content: str
    workflow_name: str = ""  # set when this message created a WorkItem (tracking chip)
    created_at: datetime


class ChatSession(_EventModel):
    id: str
    title: str
    created_at: datetime


class Features(_EventModel):
    """Feature toggles the UI adapts to (hide disabled surfaces)."""

    mail: bool = True


class RepositoryInfo(_EventModel):
    """A ManagedRepository CR projected for the settings page."""

    name: str
    provider: str
    owner: str
    repo: str
    suspended: bool = False
    require_labels: list[str] = Field(default_factory=list)
    gitops_repo_url: str = ""
    active_work_items: int = 0


DTOS: list[type[_EventModel]] = [
    Features,
    BoardItem,
    WorkflowEvent,
    UserTask,
    DraftEmail,
    ChatMessage,
    ChatSession,
    RepositoryInfo,
]
