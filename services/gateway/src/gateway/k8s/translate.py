"""WorkItem CR → BoardItem projection for the kanban UI."""

from __future__ import annotations

from datetime import datetime

from jarvis_core.dto import BoardItem
from jarvis_core.events import AnalysisVerdict, SourceType, WorkItemPhase

LABEL_REPOSITORY = "jarvis.dev/repository"


def to_board_item(cr: dict) -> BoardItem:
    meta = cr.get("metadata", {})
    spec = cr.get("spec", {})
    status = cr.get("status", {})
    source = spec.get("source", {})

    source_type = SourceType(source.get("type", "Issue"))
    if source_type == SourceType.ISSUE:
        title = source.get("issue", {}).get("title", meta.get("name", ""))
    else:
        title = source.get("featureRequest", {}).get("description", "")[:140]

    phase = WorkItemPhase(status.get("phase") or "Pending")
    analysis = status.get("analysis") or {}
    development = status.get("development") or {}

    message = status.get("failureReason") or analysis.get("summary") or ""
    verdict = AnalysisVerdict(analysis["verdict"]) if analysis.get("verdict") else None

    completed = status.get("completedAt")
    return BoardItem(
        name=meta.get("name", ""),
        repository=meta.get("labels", {}).get(LABEL_REPOSITORY)
        or spec.get("repositoryRef", {}).get("name", ""),
        title=title,
        source_type=source_type,
        phase=phase,
        message=message[:300],
        verdict=verdict,
        pr_url=development.get("prUrl", ""),
        failed=phase == WorkItemPhase.FAILED,
        created_at=_ts(meta.get("creationTimestamp")),
        updated_at=_ts(completed) if completed else None,
    )


def _ts(raw: str | None) -> datetime:
    if not raw:
        return datetime.fromtimestamp(0)
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))
