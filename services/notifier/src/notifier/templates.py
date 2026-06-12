"""Event envelope → human notification rendering, per subject."""

from __future__ import annotations

from notifier.channels.base import Notification, Severity


def render(envelope: dict, dashboard_url: str) -> Notification | None:
    """None means 'known but not notification-worthy' — router decides anyway;
    this is the content layer."""
    subject = envelope.get("type", "")
    data = envelope.get("data", {})
    event_id = envelope.get("id", "")
    name = data.get("name", "")
    repo = data.get("repository", "")
    board_link = f"{dashboard_url}/workflows/{name}" if name else dashboard_url

    common = {"event_id": event_id, "event_type": subject}

    match subject:
        case "jarvis.workflow.pr.ready":
            return Notification(
                title=f"PR ready to merge — {repo}",
                body=f"`{name}` passed CI and awaits your review.",
                url=data.get("prUrl") or board_link,
                severity=Severity.ACTION,
                fields={"Repository": repo, "PR": data.get("prUrl", ""), "Board": board_link},
                **common,
            )
        case "jarvis.workflow.pr.opened":
            return Notification(
                title=f"PR opened — {repo}",
                body=f"`{name}`: branch `{data.get('branch', '')}` is in CI.",
                url=data.get("prUrl") or board_link,
                severity=Severity.INFO,
                fields={"Repository": repo, "Board": board_link},
                **common,
            )
        case "jarvis.workflow.failed":
            return Notification(
                title=f"Workflow failed — {repo}",
                body=f"`{name}` failed in {data.get('phase', '?')}: {data.get('reason', '')[:500]}",
                url=board_link,
                severity=Severity.DANGER,
                fields={"Repository": repo},
                **common,
            )
        case "jarvis.workflow.rollout.completed":
            decision = data.get("decision", "")
            detail = data.get("gitopsPrUrl") or data.get("gitopsCommitSha", "")
            return Notification(
                title=f"Rollout {decision.lower()} — {repo}",
                body=f"`{name}` finished. {('GitOps: ' + detail) if detail else ''}",
                url=data.get("gitopsPrUrl") or board_link,
                severity=Severity.INFO,
                fields={"ArgoCD app": data.get("argocdApp", "") or "-"},
                **common,
            )
        case "jarvis.email.draft.ready":
            return Notification(
                title="Draft reply ready",
                body=f"“{data.get('subject', '')}” — {data.get('summary', '')[:300]}",
                url=f"{dashboard_url}/tasks",
                severity=Severity.ACTION,
                **common,
            )
        case "jarvis.email.task.created":
            return Notification(
                title="New task from email",
                body=f"“{data.get('title', '')}” (from {data.get('fromAddr', '')})",
                url=f"{dashboard_url}/tasks",
                severity=Severity.INFO,
                **common,
            )
        case "jarvis.workflow.created":
            return Notification(
                title=f"New work item — {repo}",
                body=f"`{name}`: {data.get('title', '')}",
                url=board_link,
                severity=Severity.INFO,
                **common,
            )
        case _:
            return None
