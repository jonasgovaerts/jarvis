"""Runtime context an agent Job assembles from its environment.

The operator passes identity via env vars; the agent fetches the full
WorkItem + ManagedRepository from the API and reads mounted secrets.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from jarvis_core import k8s
from jarvis_core.envelope import AgentFailure
from jarvis_core.forge import PROVIDERS, RepoRef

REPO_TOKEN_FILE = Path("/var/run/secrets/jarvis/repo/token")
GITOPS_TOKEN_FILE = Path("/var/run/secrets/jarvis/gitops/token")


@dataclass
class AgentContext:
    workitem: dict
    repo: dict
    namespace: str
    model: str

    @property
    def repo_ref(self) -> RepoRef:
        return RepoRef(owner=self.repo["spec"]["owner"], name=self.repo["spec"]["name"])

    @property
    def clone_url(self) -> str:
        return f"https://github.com/{self.repo_ref.full_name}.git"

    @property
    def source(self) -> dict:
        return self.workitem["spec"]["source"]

    def forge(self):
        provider = self.repo["spec"]["provider"]
        forge_cls = PROVIDERS.get(provider)
        if forge_cls is None:
            raise AgentFailure(
                reason="UnsupportedProvider",
                message=f"provider {provider!r} not implemented",
                retryable=False,
            )
        return forge_cls(repo_token())


def load_context() -> AgentContext:
    name = os.environ.get("JARVIS_WORKITEM_NAME", "")
    namespace = os.environ.get("JARVIS_WORKITEM_NAMESPACE", "")
    if not name or not namespace:
        raise AgentFailure(
            reason="MissingContext",
            message="JARVIS_WORKITEM_NAME/NAMESPACE not set",
            retryable=False,
        )
    k8s.load_config()
    workitem = k8s.get_workitem(name, namespace)
    repo = k8s.get_managed_repository(workitem["spec"]["repositoryRef"]["name"], namespace)
    return AgentContext(
        workitem=workitem,
        repo=repo,
        namespace=namespace,
        model=os.environ.get("JARVIS_MODEL", "claude-sonnet"),
    )


def repo_token() -> str:
    if REPO_TOKEN_FILE.exists():
        return REPO_TOKEN_FILE.read_text().strip()
    if token := os.environ.get("JARVIS_REPO_TOKEN", ""):
        return token
    raise AgentFailure(
        reason="MissingToken",
        message=f"no repo token at {REPO_TOKEN_FILE} or JARVIS_REPO_TOKEN",
        retryable=False,
    )


def gitops_token() -> str:
    if GITOPS_TOKEN_FILE.exists():
        return GITOPS_TOKEN_FILE.read_text().strip()
    if token := os.environ.get("JARVIS_GITOPS_TOKEN", ""):
        return token
    return repo_token()
