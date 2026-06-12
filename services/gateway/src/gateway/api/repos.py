from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from gateway.api.deps import require_token
from gateway.config import settings
from gateway.k8s import ops
from jarvis_core.dto import RepositoryInfo

router = APIRouter(prefix="/api/repos", dependencies=[Depends(require_token)])


class RepoCreate(BaseModel):
    name: str = Field(pattern=r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
    provider: str = "github"
    owner: str
    repo: str
    require_labels: list[str] = Field(default_factory=lambda: ["jarvis"], alias="requireLabels")
    credentials_secret_name: str = Field(alias="credentialsSecretName")

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def normalize_repo_url(self) -> RepoCreate:
        """Accept a pasted clone URL in the repo field: extract owner/name."""
        candidate = self.repo.strip().removesuffix(".git")
        if "github.com" in candidate or candidate.startswith(("http://", "https://", "git@")):
            parts = candidate.replace(":", "/").rstrip("/").split("/")
            if len(parts) >= 2:
                self.owner, self.repo = parts[-2], parts[-1]
        return self


@router.get("")
async def list_repos() -> list[RepositoryInfo]:
    if settings().fake_k8s:
        return []
    return await ops.list_repositories(settings().workitem_namespace)


@router.post("")
async def create_repo(body: RepoCreate) -> RepositoryInfo:
    if settings().fake_k8s:
        raise HTTPException(status_code=400, detail="not available in fixture mode")
    return await ops.create_repository(
        settings().workitem_namespace,
        name=body.name,
        provider=body.provider,
        owner=body.owner,
        repo=body.repo,
        require_labels=body.require_labels,
        credentials_secret_name=body.credentials_secret_name,
    )


@router.delete("/{name}")
async def delete_repo(name: str) -> dict:
    if settings().fake_k8s:
        raise HTTPException(status_code=400, detail="not available in fixture mode")
    await ops.delete_repository(settings().workitem_namespace, name)
    return {"status": "deleted"}
