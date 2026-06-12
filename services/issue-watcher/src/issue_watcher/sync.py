"""Core sync logic: forge issues → idempotent WorkItem creation.

Idempotency comes from deterministic WorkItem names (gh-<owner>-<repo>-<n>):
creation 409s are silently skipped, so replays and concurrent watchers are
safe without list-then-create races.
"""

from __future__ import annotations

import hashlib
import logging
import re

from jarvis_core import k8s
from jarvis_core.forge import PROVIDERS, Issue, RepoRef

log = logging.getLogger(__name__)

LABEL_REPOSITORY = "jarvis.dev/repository"
LABEL_SOURCE_TYPE = "jarvis.dev/source-type"
LABEL_ISSUE_NUMBER = "jarvis.dev/issue-number"
ANNOTATION_EXTERNAL_CLOSE = "jarvis.dev/external-close"

TERMINAL_PHASES = {"Succeeded", "Failed", "Skipped"}


def workitem_name(provider: str, owner: str, repo: str, number: int) -> str:
    """Deterministic DNS-1123 name; hash-suffixed when it would overflow."""
    prefix = {"github": "gh", "gitlab": "gl"}.get(provider, provider[:2])
    raw = f"{prefix}-{owner}-{repo}-{number}".lower()
    name = re.sub(r"[^a-z0-9-]", "-", raw).strip("-")
    name = re.sub(r"-{2,}", "-", name)
    if len(name) > 63:
        digest = hashlib.sha1(name.encode()).hexdigest()[:8]
        name = f"{name[:54]}-{digest}"
    return name


def workitem_body(mr: dict, issue: Issue) -> dict:
    mr_name = mr["metadata"]["name"]
    spec = mr["spec"]
    return {
        "apiVersion": "jarvis.dev/v1alpha1",
        "kind": "WorkItem",
        "metadata": {
            "name": workitem_name(spec["provider"], spec["owner"], spec["name"], issue.number),
            "labels": {
                LABEL_REPOSITORY: mr_name,
                LABEL_SOURCE_TYPE: "Issue",
                LABEL_ISSUE_NUMBER: str(issue.number),
            },
        },
        "spec": {
            "repositoryRef": {"name": mr_name},
            "source": {
                "type": "Issue",
                "issue": {
                    "provider": issue.provider,
                    "id": issue.id,
                    "number": issue.number,
                    "url": issue.url,
                    "title": issue.title[:200],
                    "labels": list(issue.labels),
                },
            },
        },
    }


async def sync_repository(mr: dict, namespace: str, now_iso: str) -> int:
    """One poll cycle for one ManagedRepository. Returns new WorkItem count."""
    spec = mr["spec"]
    mr_name = mr["metadata"]["name"]

    forge_cls = PROVIDERS.get(spec["provider"])
    if forge_cls is None:
        log.warning("repo %s: provider %s not supported yet", mr_name, spec["provider"])
        return 0

    token = k8s.read_secret_token(spec["credentialsSecretRef"]["name"], namespace)
    forge = forge_cls(token)
    selector = spec.get("issueSelector", {}) or {}
    try:
        issues = await forge.list_open_issues(
            RepoRef(owner=spec["owner"], name=spec["name"]),
            require_labels=selector.get("requireLabels"),
            exclude_labels=selector.get("excludeLabels"),
        )
    finally:
        await forge.aclose()

    created = 0
    if issues is not None:
        for issue in issues:
            if k8s.create_workitem(namespace, workitem_body(mr, issue)):
                log.info("created WorkItem for %s#%d: %s", mr_name, issue.number, issue.title)
                created += 1
        _suspend_externally_closed(mr_name, namespace, issues)

    k8s.patch_managed_repository_status(mr_name, namespace, {"lastIssueSync": now_iso})
    return created


def _suspend_externally_closed(mr_name: str, namespace: str, open_issues: list[Issue]) -> None:
    """Issues closed outside Jarvis: suspend their non-terminal WorkItems and
    leave the decision to delete to a human."""
    open_numbers = {issue.number for issue in open_issues}
    selector = f"{LABEL_REPOSITORY}={mr_name},{LABEL_SOURCE_TYPE}=Issue"
    for item in k8s.list_workitems(namespace, label_selector=selector):
        number = int(item["metadata"].get("labels", {}).get(LABEL_ISSUE_NUMBER, -1))
        phase = item.get("status", {}).get("phase", "")
        if number in open_numbers or number < 0 or phase in TERMINAL_PHASES:
            continue
        if item["spec"].get("suspend"):
            continue
        log.info("suspending %s: issue #%d closed externally", item["metadata"]["name"], number)
        k8s.patch_workitem(
            item["metadata"]["name"],
            namespace,
            {
                "metadata": {"annotations": {ANNOTATION_EXTERNAL_CLOSE: "true"}},
                "spec": {"suspend": True},
            },
        )
