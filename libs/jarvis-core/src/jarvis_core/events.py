"""Jarvis event contracts — the single source of truth.

NATS subject scheme: ``jarvis.<domain>.<entity>.<verb>``. Entity IDs live in the
payload, never in the subject, so consumer filters stay static and wildcard-friendly.

Every message on the wire is an :class:`EventEnvelope` whose ``type`` equals the
subject it was published on. ``SUBJECTS`` maps each subject to its payload model;
``make codegen`` exports all of this to JSON Schema and generated zod/TS.

Publisher rules (single writer per domain):
- operator publishes ``jarvis.workflow.*``
- gateway publishes ``jarvis.chat.*``, ``jarvis.task.*``, ``jarvis.email.draft.approved``
- workspace publishes ``jarvis.email.task.created`` and ``jarvis.email.draft.ready``
- notifier only consumes
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict

STREAM_NAME = "JARVIS_EVENTS"
STREAM_SUBJECTS = "jarvis.>"


class WorkItemPhase(StrEnum):
    PENDING = "Pending"
    ANALYZING = "Analyzing"
    AWAITING_DEV_APPROVAL = "AwaitingDevApproval"
    DEVELOPING = "Developing"
    AWAITING_CI = "AwaitingCI"
    AWAITING_MERGE = "AwaitingMerge"
    ROLLOUT_CHECK = "RolloutCheck"
    SUCCEEDED = "Succeeded"
    FAILED = "Failed"
    SKIPPED = "Skipped"


class AnalysisVerdict(StrEnum):
    CODE_CHANGE = "CodeChange"
    MISCONFIGURATION = "Misconfiguration"
    NOT_ACTIONABLE = "NotActionable"


class SourceType(StrEnum):
    ISSUE = "Issue"
    FEATURE_REQUEST = "FeatureRequest"


class _EventModel(BaseModel):
    """Base for all event payloads: camelCase on the wire, frozen in memory."""

    model_config = ConfigDict(
        frozen=True,
        alias_generator=lambda f: "".join(
            w if i == 0 else w.capitalize() for i, w in enumerate(f.split("_"))
        ),
        populate_by_name=True,
        serialize_by_alias=True,
    )


# --- jarvis.workflow.* (publisher: operator) ---------------------------------


class WorkflowCreated(_EventModel):
    name: str
    namespace: str
    repository: str
    source_type: SourceType
    title: str


class WorkflowPhaseChanged(_EventModel):
    name: str
    repository: str
    from_phase: WorkItemPhase
    to_phase: WorkItemPhase
    message: str = ""


class WorkflowAnalysisCompleted(_EventModel):
    name: str
    repository: str
    verdict: AnalysisVerdict
    summary: str
    confidence: str = ""


class WorkflowPROpened(_EventModel):
    name: str
    repository: str
    pr_url: str
    pr_number: int
    branch: str


class WorkflowPRReady(_EventModel):
    """CI is green; the PR awaits a human merge. The 'ready to merge' notification."""

    name: str
    repository: str
    pr_url: str
    pr_number: int


class WorkflowRolloutCompleted(_EventModel):
    name: str
    repository: str
    decision: str  # Required | NotRequired
    gitops_commit_sha: str = ""
    gitops_pr_url: str = ""
    argocd_app: str = ""


class WorkflowFailed(_EventModel):
    name: str
    repository: str
    phase: WorkItemPhase
    reason: str


# --- jarvis.chat.* / jarvis.task.* (publisher: gateway) ----------------------


class ChatRequestCreated(_EventModel):
    session_id: str
    workflow_name: str
    repository: str
    title: str


class TaskCompleted(_EventModel):
    task_id: str


# --- jarvis.email.* (publisher: workspace; draft.approved: gateway) ----------


class EmailTaskCreated(_EventModel):
    task_id: str
    gmail_message_id: str
    thread_id: str
    subject: str
    from_addr: str
    title: str
    priority: str = "normal"


class EmailDraftReady(_EventModel):
    task_id: str
    gmail_message_id: str
    gmail_draft_id: str
    thread_id: str
    subject: str
    summary: str


class EmailDraftApproved(_EventModel):
    task_id: str
    gmail_draft_id: str


# --- Envelope -----------------------------------------------------------------


class EventEnvelope(_EventModel):
    """CloudEvents-lite wrapper for every message on JARVIS_EVENTS."""

    id: str
    type: str  # always equals the NATS subject
    source: str  # publishing service name: operator | gateway | workspace
    time: datetime
    data: dict[str, Any]


SUBJECTS: dict[str, type[_EventModel]] = {
    "jarvis.workflow.created": WorkflowCreated,
    "jarvis.workflow.phase.changed": WorkflowPhaseChanged,
    "jarvis.workflow.analysis.completed": WorkflowAnalysisCompleted,
    "jarvis.workflow.pr.opened": WorkflowPROpened,
    "jarvis.workflow.pr.ready": WorkflowPRReady,
    "jarvis.workflow.rollout.completed": WorkflowRolloutCompleted,
    "jarvis.workflow.failed": WorkflowFailed,
    "jarvis.chat.request.created": ChatRequestCreated,
    "jarvis.task.completed": TaskCompleted,
    "jarvis.email.task.created": EmailTaskCreated,
    "jarvis.email.draft.ready": EmailDraftReady,
    "jarvis.email.draft.approved": EmailDraftApproved,
}


def make_envelope(subject: str, payload: _EventModel, *, source: str) -> EventEnvelope:
    """Build a wire-ready envelope, validating the payload type against SUBJECTS."""
    expected = SUBJECTS.get(subject)
    if expected is None:
        raise ValueError(f"unknown subject: {subject}")
    if not isinstance(payload, expected):
        raise TypeError(
            f"subject {subject} expects {expected.__name__}, got {type(payload).__name__}"
        )
    return EventEnvelope(
        id=str(uuid.uuid4()),
        type=subject,
        source=source,
        time=datetime.now(UTC),
        data=payload.model_dump(mode="json", by_alias=True),
    )


def parse_payload(envelope: EventEnvelope) -> _EventModel | None:
    """Return the typed payload for a known subject, or None for unknown ones."""
    model = SUBJECTS.get(envelope.type)
    if model is None:
        return None
    return model.model_validate(envelope.data)
