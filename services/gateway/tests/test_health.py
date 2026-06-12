from fastapi.testclient import TestClient

from gateway.main import create_app


def test_healthz():
    client = TestClient(create_app())
    response = client.get("/api/healthz")
    assert response.status_code == 200
    assert response.json()["service"] == "gateway"


def test_readyz():
    client = TestClient(create_app())
    assert client.get("/api/readyz").status_code == 200
