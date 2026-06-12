"""Agent result envelope — the contract between agent Jobs and the operator.

An agent's last act is writing this envelope as JSON to ``/dev/termination-log``.
The operator reads it from the pod's terminated-container state, so the message
must stay under Kubernetes' 4096-byte termination-message limit. Anything bigger
(full analysis reports, CI log digests) goes into a ConfigMap owned by the
WorkItem and is referenced by name in ``artifacts``.
"""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

TERMINATION_LOG = Path("/dev/termination-log")
MAX_BYTES = 4096
# Leave room for envelope structure when truncating long error messages.
_TRUNCATION_SUFFIX = "…[truncated]"


class AgentStage(StrEnum):
    ANALYZER = "analyzer"
    DEVELOPER = "developer"
    DEVOPS = "devops"
    SRE = "sre"


class AgentError(BaseModel):
    reason: str  # short machine-readable cause, e.g. "RateLimited", "CloneFailed"
    message: str
    retryable: bool


class AgentFailure(Exception):
    """Raise anywhere in an agent to fail the stage with explicit retry
    semantics; the CLI turns it into a failure envelope."""

    def __init__(self, reason: str, message: str, *, retryable: bool):
        super().__init__(f"{reason}: {message}")
        self.reason = reason
        self.message = message
        self.retryable = retryable


class AgentResultEnvelope(BaseModel):
    version: Literal[1] = 1
    outcome: Literal["success", "failure"]
    stage: AgentStage
    result: dict[str, Any] | None = None
    artifacts: dict[str, str] = Field(default_factory=dict)  # logical name -> ConfigMap name
    error: AgentError | None = None

    def to_wire(self) -> str:
        """Serialize, shrinking oversized free-text fields to fit MAX_BYTES."""
        raw = self.model_dump_json()
        if len(raw.encode()) <= MAX_BYTES:
            return raw

        # Shrink the largest free-text fields first; structured fields stay intact.
        slim = self.model_copy(deep=True)
        if slim.error is not None and len(slim.error.message) > 256:
            slim.error.message = slim.error.message[:256] + _TRUNCATION_SUFFIX
        if slim.result:
            for key, value in slim.result.items():
                if isinstance(value, str) and len(value) > 512:
                    slim.result[key] = value[:512] + _TRUNCATION_SUFFIX
        raw = slim.model_dump_json()
        if len(raw.encode()) > MAX_BYTES:
            raise ValueError(
                f"agent envelope still exceeds {MAX_BYTES} bytes after truncation; "
                "move large payloads to an artifact ConfigMap"
            )
        return raw


def success(
    stage: AgentStage, result: dict[str, Any], *, artifacts: dict[str, str] | None = None
) -> AgentResultEnvelope:
    return AgentResultEnvelope(
        outcome="success", stage=stage, result=result, artifacts=artifacts or {}
    )


def failure(
    stage: AgentStage, reason: str, message: str, *, retryable: bool
) -> AgentResultEnvelope:
    return AgentResultEnvelope(
        outcome="failure",
        stage=stage,
        error=AgentError(reason=reason, message=message, retryable=retryable),
    )


def write_termination_message(envelope: AgentResultEnvelope, path: Path = TERMINATION_LOG) -> None:
    path.write_text(envelope.to_wire())


def parse_termination_message(raw: str) -> AgentResultEnvelope:
    return AgentResultEnvelope.model_validate(json.loads(raw))
