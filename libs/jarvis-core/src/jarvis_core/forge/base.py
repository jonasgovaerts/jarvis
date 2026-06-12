from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class RepoRef:
    owner: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


@dataclass(frozen=True)
class Issue:
    provider: str
    id: str  # provider-global id (GitHub node_id) — the dedupe key
    number: int
    url: str
    title: str
    body: str
    labels: tuple[str, ...] = field(default_factory=tuple)
    state: str = "open"


@dataclass(frozen=True)
class PullRequest:
    number: int
    url: str
    head_sha: str
    head_ref: str
    merged: bool = False
    merge_sha: str = ""
    state: str = "open"


@dataclass(frozen=True)
class CheckRun:
    name: str
    status: str  # queued | in_progress | completed
    conclusion: str  # success | failure | cancelled | skipped | ... ("" until completed)
    url: str = ""

    @property
    def finished_ok(self) -> bool:
        return self.status == "completed" and self.conclusion in {"success", "skipped", "neutral"}

    @property
    def finished_bad(self) -> bool:
        return self.status == "completed" and not self.finished_ok


class IssueProvider(Protocol):
    """The part of a forge the issue-watcher and analyzer need."""

    provider_name: str

    async def list_open_issues(
        self,
        repo: RepoRef,
        *,
        require_labels: list[str] | None = None,
        exclude_labels: list[str] | None = None,
    ) -> list[Issue] | None:
        """Open issues matching the selector; None means unchanged since the
        last call (conditional request hit)."""
        ...

    async def get_issue(self, repo: RepoRef, number: int) -> Issue: ...
