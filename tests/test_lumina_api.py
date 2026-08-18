from fastapi.testclient import TestClient

from services.api.app.main import create_app


def test_lumina_api_health():
    response = TestClient(create_app()).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "lumina-api"}


def test_component_status_reports_healthy_and_degraded(monkeypatch):
    async def healthy(*args, **kwargs):
        return {"status": "healthy"}

    async def unavailable(*args, **kwargs):
        return {"status": "unavailable"}

    monkeypatch.setattr("services.api.app.main.archive_health", healthy)
    monkeypatch.setattr("services.api.app.main.PRomopClient.health", healthy)
    monkeypatch.setattr("services.api.app.main.WearablesClient.health", healthy)
    client = TestClient(create_app())
    assert client.get("/api/v1/status").json()["status"] == "healthy"

    monkeypatch.setattr("services.api.app.main.WearablesClient.health", unavailable)
    assert client.get("/api/v1/status").json()["status"] == "degraded"
