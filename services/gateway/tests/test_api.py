from fastapi.testclient import TestClient

from gateway.main import create_app


def client() -> TestClient:
    return TestClient(create_app())


def test_workflows_served_from_fixture_cache():
    with client() as c:
        items = c.get("/api/workflows").json()
        assert len(items) >= 8
        names = {i["name"] for i in items}
        assert "gh-acme-api-42" in names
        # camelCase wire format
        assert "createdAt" in items[0]
        assert "sourceType" in items[0]


def test_workflows_phase_filter():
    with client() as c:
        items = c.get("/api/workflows", params={"phase": "Analyzing"}).json()
        assert items and all(i["phase"] == "Analyzing" for i in items)


def test_workflow_detail_and_404():
    with client() as c:
        detail = c.get("/api/workflows/gh-acme-api-42").json()
        assert detail["item"]["name"] == "gh-acme-api-42"
        assert detail["history"] == []
        assert c.get("/api/workflows/nope").status_code == 404


def test_action_in_fixture_mode():
    with client() as c:
        response = c.post("/api/workflows/gh-acme-api-42/actions", json={"action": "retry"})
        assert response.status_code == 200
        assert response.json()["status"] == "accepted"


def test_invalid_action_rejected():
    with client() as c:
        response = c.post("/api/workflows/gh-acme-api-42/actions", json={"action": "explode"})
        assert response.status_code == 422


def test_auth_enforced(monkeypatch):
    from gateway import config

    monkeypatch.setenv("JARVIS_TOKEN", "sekrit")
    config.settings.cache_clear()
    try:
        with client() as c:
            assert c.get("/api/workflows").status_code == 401
            ok = c.get("/api/workflows", headers={"Authorization": "Bearer sekrit"})
            assert ok.status_code == 200
    finally:
        monkeypatch.delenv("JARVIS_TOKEN")
        config.settings.cache_clear()


def test_chat_session_roundtrip():
    with client() as c:
        session = c.post("/api/chat/sessions", json={"title": "test"}).json()
        assert session["title"] == "test"
        sessions = c.get("/api/chat/sessions").json()
        assert any(s["id"] == session["id"] for s in sessions)
        assert c.get(f"/api/chat/sessions/{session['id']}/messages").json() == []


def test_tasks_empty_and_drafts_empty():
    with client() as c:
        assert c.get("/api/tasks").json() == []
        assert c.get("/api/drafts").json() == []
