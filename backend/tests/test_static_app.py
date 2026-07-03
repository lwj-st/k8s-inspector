from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_root_serves_index_html(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>hello</body></html>", encoding="utf-8")

    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", frontend_dist_path=str(dist)))
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "hello" in response.text


def test_assets_route_serves_compiled_asset(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    (assets / "app.js").write_text("console.log('ok')", encoding="utf-8")

    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", frontend_dist_path=str(dist)))
    client = TestClient(app)

    response = client.get("/assets/app.js")

    assert response.status_code == 200
    assert "console.log('ok')" in response.text


def test_base_path_serves_index_html(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>base-path</body></html>", encoding="utf-8")

    app = create_app(
        Settings(
            base_path="/inspector",
            database_url=f"sqlite:///{tmp_path / 'test.db'}",
            frontend_dist_path=str(dist),
        )
    )
    client = TestClient(app)

    response = client.get("/inspector")

    assert response.status_code == 200
    assert "base-path" in response.text


def test_spa_fallback_does_not_capture_api_paths(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>fallback</body></html>", encoding="utf-8")

    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", frontend_dist_path=str(dist)))
    client = TestClient(app)

    response = client.get("/api/not-found")

    assert response.status_code == 404
