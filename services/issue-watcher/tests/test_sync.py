from issue_watcher.sync import workitem_body, workitem_name
from jarvis_core.forge import Issue


def test_workitem_name_deterministic_and_sanitized():
    assert workitem_name("github", "Acme", "My.Repo", 42) == "gh-acme-my-repo-42"
    assert workitem_name("github", "acme", "api", 42) == workitem_name("github", "acme", "api", 42)


def test_workitem_name_length_capped_with_hash():
    name = workitem_name("github", "a" * 40, "b" * 40, 123456)
    assert len(name) <= 63
    assert name[:3] == "gh-"
    # Same input → same hash suffix.
    assert name == workitem_name("github", "a" * 40, "b" * 40, 123456)


def test_workitem_body_contract():
    mr = {
        "metadata": {"name": "my-repo"},
        "spec": {"provider": "github", "owner": "acme", "name": "api"},
    }
    issue = Issue(
        provider="github",
        id="I_x",
        number=7,
        url="https://github.com/acme/api/issues/7",
        title="fix it",
        body="...",
        labels=("jarvis",),
    )
    body = workitem_body(mr, issue)
    assert body["metadata"]["name"] == "gh-acme-api-7"
    assert body["metadata"]["labels"]["jarvis.dev/repository"] == "my-repo"
    assert body["metadata"]["labels"]["jarvis.dev/issue-number"] == "7"
    assert body["spec"]["repositoryRef"]["name"] == "my-repo"
    assert body["spec"]["source"]["type"] == "Issue"
    assert body["spec"]["source"]["issue"]["id"] == "I_x"
