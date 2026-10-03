from fastapi.testclient import TestClient

from algotrade_api import __version__


def test_health_reports_store_latest_session_and_versions(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["storage"] == "memory"
    assert body["latest_session"] == "2022-11-23"
    assert "bars/1d" in body["tables"]
    assert body["versions"]["api"] == __version__
    assert body["versions"]["schema"] == "1"
