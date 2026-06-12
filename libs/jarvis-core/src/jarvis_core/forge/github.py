from __future__ import annotations

import httpx

from jarvis_core.forge.base import Issue, RepoRef

API = "https://api.github.com"


class GitHubForge:
    """GitHub REST client scoped to what Jarvis needs.

    Conditional requests: list_open_issues sends If-None-Match per repo and
    returns None on 304, so pollers pay ~0 rate-limit cost on quiet repos.
    """

    provider_name = "github"

    def __init__(self, token: str, client: httpx.AsyncClient | None = None):
        self._client = client or httpx.AsyncClient(base_url=API, timeout=30)
        self._client.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )
        self._etags: dict[str, str] = {}

    async def aclose(self) -> None:
        await self._client.aclose()

    async def list_open_issues(
        self,
        repo: RepoRef,
        *,
        require_labels: list[str] | None = None,
        exclude_labels: list[str] | None = None,
    ) -> list[Issue] | None:
        path = f"/repos/{repo.owner}/{repo.name}/issues"
        headers = {}
        # GitHub's labels query param is AND semantics — exactly what
        # requireLabels means. Conditional request key includes the selector.
        params = {"state": "open", "per_page": "100"}
        if require_labels:
            params["labels"] = ",".join(require_labels)
        etag_key = f"{repo.full_name}?{params.get('labels', '')}"
        if etag := self._etags.get(etag_key):
            headers["If-None-Match"] = etag

        response = await self._client.get(path, params=params, headers=headers)
        if response.status_code == 304:
            return None
        response.raise_for_status()
        if etag := response.headers.get("ETag"):
            self._etags[etag_key] = etag

        excluded = set(exclude_labels or [])
        issues = []
        for raw in response.json():
            if "pull_request" in raw:  # GitHub returns PRs as issues
                continue
            issue = _to_issue(raw)
            if excluded & set(issue.labels):
                continue
            issues.append(issue)
        return issues

    async def get_issue(self, repo: RepoRef, number: int) -> Issue:
        response = await self._client.get(f"/repos/{repo.owner}/{repo.name}/issues/{number}")
        response.raise_for_status()
        return _to_issue(response.json())


def _to_issue(raw: dict) -> Issue:
    return Issue(
        provider="github",
        id=raw["node_id"],
        number=raw["number"],
        url=raw["html_url"],
        title=raw["title"],
        body=raw.get("body") or "",
        labels=tuple(label["name"] for label in raw.get("labels", [])),
        state=raw["state"],
    )
