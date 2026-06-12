from __future__ import annotations

import httpx

from jarvis_core.forge.base import CheckRun, Issue, PullRequest, RepoRef

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

    async def get_default_branch(self, repo: RepoRef) -> str:
        response = await self._client.get(f"/repos/{repo.owner}/{repo.name}")
        response.raise_for_status()
        return response.json()["default_branch"]

    async def create_pull_request(
        self, repo: RepoRef, *, head: str, base: str, title: str, body: str
    ) -> PullRequest:
        response = await self._client.post(
            f"/repos/{repo.owner}/{repo.name}/pulls",
            json={"head": head, "base": base, "title": title, "body": body},
        )
        response.raise_for_status()
        return _to_pr(response.json())

    async def find_pull_request(self, repo: RepoRef, *, head: str) -> PullRequest | None:
        """Open PR for a head branch, if one exists (used by CI fix loops)."""
        response = await self._client.get(
            f"/repos/{repo.owner}/{repo.name}/pulls",
            params={"head": f"{repo.owner}:{head}", "state": "open"},
        )
        response.raise_for_status()
        items = response.json()
        return _to_pr(items[0]) if items else None

    async def get_pull_request(self, repo: RepoRef, number: int) -> PullRequest:
        response = await self._client.get(f"/repos/{repo.owner}/{repo.name}/pulls/{number}")
        response.raise_for_status()
        return _to_pr(response.json())

    async def merge_pull_request(self, repo: RepoRef, number: int) -> str:
        """Squash-merge; returns the merge commit SHA."""
        response = await self._client.put(
            f"/repos/{repo.owner}/{repo.name}/pulls/{number}/merge",
            json={"merge_method": "squash"},
        )
        response.raise_for_status()
        return response.json().get("sha", "")

    async def list_check_runs(self, repo: RepoRef, sha: str) -> list[CheckRun]:
        response = await self._client.get(
            f"/repos/{repo.owner}/{repo.name}/commits/{sha}/check-runs",
            params={"per_page": "100"},
        )
        response.raise_for_status()
        return [
            CheckRun(
                name=raw["name"],
                status=raw["status"],
                conclusion=raw.get("conclusion") or "",
                url=raw.get("html_url") or "",
            )
            for raw in response.json().get("check_runs", [])
        ]


def _to_pr(raw: dict) -> PullRequest:
    return PullRequest(
        number=raw["number"],
        url=raw["html_url"],
        head_sha=raw["head"]["sha"],
        head_ref=raw["head"]["ref"],
        merged=bool(raw.get("merged") or raw.get("merged_at")),
        merge_sha=raw.get("merge_commit_sha") or "",
        state=raw["state"],
    )


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
