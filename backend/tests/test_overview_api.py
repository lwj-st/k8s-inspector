from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_health_routes_under_root_base_path() -> None:
    app = create_app(Settings(base_path="", database_url="sqlite:///./root-test.db"))
    client = TestClient(app)

    response = client.get("/api/v1/overview")

    assert response.status_code == 200
    assert response.json()["health_status"] == "warning"


def test_health_routes_under_sub_path() -> None:
    app = create_app(Settings(base_path="/inspector", database_url="sqlite:///./subpath-test.db"))
    client = TestClient(app)

    response = client.get("/inspector/api/v1/overview")

    assert response.status_code == 200
