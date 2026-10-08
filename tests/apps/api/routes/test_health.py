import json
from pathlib import Path

from fastapi.testclient import TestClient

from algotrade.config.site.users import Role
from algotrade.config.user import UserContext
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade_api import __version__
from algotrade_api.auth.protocol import UnauthenticatedError
from algotrade_api.deps import ApiSettings
from algotrade_api.graphql.schema import sdl
from algotrade_api.main import create_app
from algotrade_api.ops.build import STAMP, schema_hash
from tests.helpers.api_store import as_user, store_over


class Anonymous:
    def authenticate(self, request: object) -> None:
        raise UnauthenticatedError("no credentials")


def test_only_an_admin_reads_the_stored_table_names(
    api_golden: tuple[object, dict[str, str]],
) -> None:
    """ADR 0056: anyone else gets the status without table names (health is public)."""
    store = api_golden[0]
    settings = ApiSettings("memory://", "config")
    admin = TestClient(create_app(settings, store, authenticator=as_user())).get("/health")  # type: ignore[arg-type]
    trader = TestClient(create_app(settings, store, authenticator=as_user("bob", Role.TRADER)))  # type: ignore[arg-type]
    anonymous = TestClient(create_app(settings, store, authenticator=Anonymous()))  # type: ignore[arg-type]
    assert "bars/1d" in admin.json()["tables"]
    for client in (trader, anonymous):
        body = client.get("/health").json()
        assert body["status"] == "ok" and body["tables"] == []
        assert "rollups/" not in json.dumps(body) and "bars/" not in json.dumps(body)


def test_health_reports_store_latest_session_and_versions(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["storage"] == "memory"
    assert body["latest_session"] == "2022-11-23"
    assert "bars/1d" in body["tables"]
    assert body["versions"]["api"] == __version__
    assert body["versions"]["schema"] == "1"


def test_an_empty_store_has_no_session_and_reports_its_kind() -> None:
    store = store_over(MemoryBackend(), MemoryConfigStore({}), UserContext("local"), "file://x")
    body = (
        TestClient(create_app(ApiSettings("memory://", "config"), store, authenticator=as_user()))
        .get("/health")
        .json()
    )
    assert (body["storage"], body["latest_session"], body["tables"]) == ("file", None, [])


def test_health_reports_the_build_the_api_started_with_and_what_disagrees(
    client: TestClient,
) -> None:
    build = client.get("/health").json()["build"]
    assert build["api"]["schema_hash"] == schema_hash(sdl())
    assert build["web"] is None  # no web served by the test app
    assert build["stale"] is bool(build["mismatches"])


def test_a_served_web_built_against_another_schema_makes_health_stale(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<!doctype html>")
    (tmp_path / STAMP).write_text(
        json.dumps(
            {"git_sha": "abc", "schema_hash": "0" * 12, "built_at": "2999-01-01T00:00:00+00:00"}
        )
    )
    store = store_over(MemoryBackend(), MemoryConfigStore({}), UserContext("local"), "file://x")
    settings = ApiSettings("memory://", "config", web_dist=tmp_path)
    build = (
        TestClient(create_app(settings, store, authenticator=as_user()))
        .get("/health")
        .json()["build"]
    )
    assert build["stale"] and build["web"]["schema_hash"] == "0" * 12
    assert any("fields the API lacks" in m and "kickstart" in m for m in build["mismatches"])
