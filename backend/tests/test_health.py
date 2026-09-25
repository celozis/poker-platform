from fastapi.testclient import TestClient


def test_health_reports_api_and_database_available(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"api": "ok", "database": "ok"}
