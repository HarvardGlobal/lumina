from fastapi.testclient import TestClient

from services.api.app.main import create_app


def test_lumina_api_health():
    response = TestClient(create_app()).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "lumina-api"}
