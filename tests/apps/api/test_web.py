"""The built web app on the API's origin (ADR 0044): files of the build, the SPA fallback to
index.html, API routes first, nothing outside the build directory, and ``ALGOTRADE_AUTH=off``
still refusing what a tunnel forwards."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from algotrade.config.site.users import Role, UserRecord
from algotrade.core.model.errors import ConfigurationError
from algotrade_api.auth.local import LocalAuthenticator
from algotrade_api.deps import ApiSettings
from algotrade_api.main import create_app
from algotrade_api.web import IMMUTABLE, REVALIDATE, build_file, web_router
from tests.helpers.api_store import as_user

INDEX = "<!doctype html><title>algotrade</title><div id=root></div>"
SCRIPT = "console.log('app')"
VIEWER = {"query": "{ viewer { id } }"}


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    """A web build (index.html, a hashed asset, a root file) and a secret beside it."""
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text(INDEX)
    (root / "assets" / "app-1a2b.js").write_text(SCRIPT)
    (root / "favicon.svg").write_text("<svg/>")
    (tmp_path / "secret.txt").write_text("not for the web")
    (root / "assets" / "escape.js").symlink_to(tmp_path / "secret.txt")
    return root


@pytest.fixture
def client(dist: Path) -> TestClient:
    settings = ApiSettings("memory://", "config", web_dist=dist)
    return TestClient(create_app(settings, authenticator=as_user()))


@pytest.mark.parametrize("path", ["/", "/login", "/screeners/abc/edit", "/admin/ingestion"])
def test_a_page_path_answers_the_app(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    assert response.text == INDEX
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == REVALIDATE["Cache-Control"]


def test_a_build_file_is_served_and_hashed_assets_are_cached_for_good(client: TestClient) -> None:
    script = client.get("/assets/app-1a2b.js")
    assert (script.status_code, script.text) == (200, SCRIPT)
    assert "javascript" in script.headers["content-type"]
    assert script.headers["cache-control"] == IMMUTABLE["Cache-Control"]
    icon = client.get("/favicon.svg")
    assert icon.status_code == 200 and icon.headers["cache-control"] == "no-cache"


def test_a_big_asset_is_gzipped_on_request(dist: Path, client: TestClient) -> None:
    (dist / "assets" / "big-3c4d.js").write_text("console.log('app');\n" * 500)
    response = client.get("/assets/big-3c4d.js", headers={"Accept-Encoding": "gzip"})
    assert response.headers["content-encoding"] == "gzip"
    assert response.text.startswith("console.log")


@pytest.mark.parametrize("path", ["/screeners/preview", "/features/check"])
def test_a_get_on_a_post_only_api_path_is_405_not_the_app(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 405 and response.text != INDEX


def test_head_answers_like_get_without_a_body(client: TestClient) -> None:
    response = client.head("/login")
    assert response.status_code == 200 and response.content == b""
    assert response.headers["content-type"].startswith("text/html")


def test_a_missing_asset_is_404_not_the_app(client: TestClient) -> None:
    assert client.get("/assets/app-old.js").status_code == 404


def test_api_routes_keep_precedence(client: TestClient) -> None:
    assert client.get("/health").json()["status"] == "ok"
    assert client.post("/graphql", json=VIEWER).json()["data"]["viewer"]["id"] == "local"
    assert client.get("/openapi.json").json()["info"]["title"] == "algotrade API"
    assert "swagger" in client.get("/docs").text.lower()
    assert client.get("/graphql").status_code != 200  # GraphiQL off: never the web app


@pytest.mark.parametrize(
    "path",
    ["../secret.txt", "../../etc/passwd", "/etc/passwd", "assets/escape.js", "a\x00b", "x" * 5000],
)
def test_no_path_leaves_the_build_directory(dist: Path, path: str) -> None:
    assert build_file(dist.resolve(), path) is None


@pytest.mark.parametrize("url", ["/%2e%2e/secret.txt", "/assets/%2e%2e/%2e%2e/secret.txt"])
def test_an_encoded_traversal_answers_no_file_outside(client: TestClient, url: str) -> None:
    response = client.get(url)
    assert "not for the web" not in response.text
    assert response.status_code in (200, 404)


def test_unset_serves_no_files() -> None:
    client = TestClient(create_app(ApiSettings("memory://", "config"), authenticator=as_user()))
    assert client.get("/login").status_code == 404
    assert client.get("/").status_code == 404


def test_a_directory_without_a_build_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="make web-build"):
        web_router(tmp_path)


def test_settings_read_the_build_directory_from_the_environment(
    dist: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ALGOTRADE_DATA_URL", "memory://")
    monkeypatch.setenv("ALGOTRADE_WEB_DIST", str(dist))
    assert ApiSettings.from_env().web_dist == dist


@pytest.mark.parametrize("header", ["X-Forwarded-For", "Forwarded", "Tailscale-Funnel-Request"])
def test_auth_off_serves_the_page_but_refuses_forwarded_api_calls(dist: Path, header: str) -> None:
    """Funnel hands requests to the API on loopback: with ``ALGOTRADE_AUTH=off`` the headers
    a tunnel adds make every API call 401 (ADR 0040, 0044); the page itself holds no data."""
    local = LocalAuthenticator(UserRecord("local", Role.ADMIN))
    app = create_app(ApiSettings("memory://", "config", web_dist=dist), authenticator=local)
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    assert client.post("/graphql", json=VIEWER).status_code == 200
    forwarded = {header: "203.0.113.9"}
    assert client.post("/graphql", json=VIEWER, headers=forwarded).status_code == 401
    assert client.get("/login", headers=forwarded).text == INDEX
