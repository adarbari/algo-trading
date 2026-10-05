from fastapi.testclient import TestClient

from algotrade.config.user import UserContext
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade_api import __version__
from algotrade_api.deps import ApiSettings
from algotrade_api.main import create_app
from tests.helpers.api_store import store_over


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
    body = TestClient(create_app(ApiSettings("memory://", "config"), store)).get("/health").json()
    assert (body["storage"], body["latest_session"], body["tables"]) == ("file", None, [])
