import httpx
import pytest

from jarvis_core.forge import GitHubForge, RepoRef

REPO = RepoRef(owner="acme", name="api")


def fake_issue(
    number: int, title: str = "t", labels: list[str] | None = None, pr: bool = False
) -> dict:
    raw = {
        "node_id": f"I_{number}",
        "number": number,
        "html_url": f"https://github.com/acme/api/issues/{number}",
        "title": title,
        "body": "body",
        "labels": [{"name": label} for label in (labels or [])],
        "state": "open",
    }
    if pr:
        raw["pull_request"] = {"url": "..."}
    return raw


def forge_with(handler) -> GitHubForge:
    client = httpx.AsyncClient(
        base_url="https://api.github.com", transport=httpx.MockTransport(handler)
    )
    return GitHubForge("tok", client=client)


async def test_list_filters_prs_and_excluded_labels():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer tok"
        return httpx.Response(
            200,
            json=[
                fake_issue(1, labels=["jarvis"]),
                fake_issue(2, labels=["jarvis", "wontfix"]),
                fake_issue(3, pr=True),
            ],
            headers={"ETag": 'W/"abc"'},
        )

    forge = forge_with(handler)
    issues = await forge.list_open_issues(
        REPO, require_labels=["jarvis"], exclude_labels=["wontfix"]
    )
    assert [issue.number for issue in issues] == [1]
    assert issues[0].id == "I_1"


async def test_etag_304_returns_none():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            assert "If-None-Match" not in request.headers
            return httpx.Response(200, json=[fake_issue(1)], headers={"ETag": 'W/"abc"'})
        assert request.headers["If-None-Match"] == 'W/"abc"'
        return httpx.Response(304)

    forge = forge_with(handler)
    first = await forge.list_open_issues(REPO)
    assert len(first) == 1
    second = await forge.list_open_issues(REPO)
    assert second is None


async def test_require_labels_sent_as_query():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["labels"] == "jarvis,bug"
        return httpx.Response(200, json=[])

    forge = forge_with(handler)
    assert await forge.list_open_issues(REPO, require_labels=["jarvis", "bug"]) == []


async def test_get_issue():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/acme/api/issues/42"
        return httpx.Response(200, json=fake_issue(42, title="the bug"))

    forge = forge_with(handler)
    issue = await forge.get_issue(REPO, 42)
    assert issue.title == "the bug"
    assert issue.body == "body"


async def test_http_error_raises():
    forge = forge_with(lambda request: httpx.Response(401, json={"message": "bad"}))
    with pytest.raises(httpx.HTTPStatusError):
        await forge.list_open_issues(REPO)


async def test_create_issue_comment():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/acme/api/issues/42/comments"
        import json

        assert "Jarvis" in json.loads(request.content)["body"]
        return httpx.Response(
            201, json={"html_url": "https://github.com/acme/api/issues/42#issuecomment-1"}
        )

    forge = forge_with(handler)
    url = await forge.create_issue_comment(REPO, 42, "## 🤖 Jarvis analysis\n\nok")
    assert url.endswith("#issuecomment-1")
