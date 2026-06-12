"""Provider-agnostic forge clients (issues, PRs, checks).

GitHub is implemented; GitLab slots in later by registering another
IssueProvider implementation in PROVIDERS.
"""

from jarvis_core.forge.base import CheckRun, Issue, IssueProvider, PullRequest, RepoRef
from jarvis_core.forge.github import GitHubForge

PROVIDERS: dict[str, type] = {
    "github": GitHubForge,
}

__all__ = [
    "CheckRun",
    "Issue",
    "IssueProvider",
    "PullRequest",
    "RepoRef",
    "GitHubForge",
    "PROVIDERS",
]
