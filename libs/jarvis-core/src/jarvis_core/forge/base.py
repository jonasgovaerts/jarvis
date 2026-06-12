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
