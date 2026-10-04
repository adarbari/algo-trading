from pathlib import Path

from fastapi.testclient import TestClient

from algotrade.config.user import UserContext
from algotrade.services.explore.store import store_over
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import FileConfigStore
from algotrade_api.deps import ApiSettings
from algotrade_api.main import create_app


def test_screen_configs_with_latest_run(client: TestClient) -> None:
    configs = client.get("/screens").json()
    assert [c["config"]["config_id"] for c in configs] == ["short_premium_liquidity", "vrp_scanner"]
    assert configs[0]["config"]["schedule"] == "nightly"
    assert configs[0]["latest_session"] == "2022-11-23"


def test_screen_results_with_audit_and_decision_filter(client: TestClient) -> None:
    body = client.get("/screens/short_premium_liquidity/results").json()
    assert (body["user"], body["session"]) == ("site", "2022-11-23")
    assert body["decisions"] == {"QUALIFIED": 1, "REJECTED": 1}
    assert body["audit"]["coverage"] == "COMPLETE"
    rows = body["page"]["items"]
    assert [(r["symbol"], r["decision"]) for r in rows] == [
        ("AAA", "QUALIFIED"),
        ("BBB", "REJECTED"),
    ]
    assert rows[0]["values"] == {"put_tier": "A"}
    only = client.get("/screens/short_premium_liquidity/results?decision=rejected").json()
    assert [r["symbol"] for r in only["page"]["items"]] == ["BBB"]


def test_screen_results_not_found(client: TestClient) -> None:
    assert client.get("/screens/sma_trend/results").status_code == 404  # a strategy
    assert client.get("/screens/nope/results").status_code == 404
    early = client.get("/screens/short_premium_liquidity/results", params={"date": "2021-01-04"})
    assert early.status_code == 404


def test_ideas_one_row_per_ticker_ranked_with_every_pick(client: TestClient) -> None:
    body = client.get("/ideas").json()
    assert (body["session"], body["total"], body["priority"]) == ("2022-11-23", 2, [])
    first, second = body["items"]
    # No priority stored: screens rank by id (premium < vrp), then score: AAA (100) first.
    assert (first["rank"], first["symbol"]) == (1, "AAA")
    assert [(p["config_id"], p["decision"]) for p in first["picks"]] == [
        ("premium", "QUALIFIED"),
        ("vrp", "QUALIFIED"),
    ]
    assert first["picks"][1]["columns"] == {"spread": 0.05}
    assert first["picks"][1]["criterion_values"] == {"iv30": 0.62}
    assert (first["picks"][0]["flags"], first["picks"][1]["flags"]) == ([], ["leveraged_inverse"])
    assert body["screeners"] == [
        {"config_id": c, "user": "site", "name": c, "version": 1} for c in ("premium", "vrp")
    ]
    assert (first["next_earnings_date"], first["days_to_earnings"]) == ("2022-12-01", 6)
    assert first["closest_expiry_dte"] == 30  # the nearest stored expiry (2022-12-23)
    assert first["earnings_before_expiry"] is True  # earnings 2022-12-01
    assert second["symbol"] == "BBB"
    near = second["picks"][0]
    assert near["reasons"] == "iv rank 40 < 50"
    assert near["criteria"] == [
        {
            "criterion_id": "iv_rank",
            "field": "iv_rank",
            "outcome": "NEAR",
            "value": 40.0,
            "distance": 10.0,
        }
    ]
    assert (second["next_earnings_date"], second["days_to_earnings"]) == (None, None)


def test_ideas_limit_and_date(client: TestClient) -> None:
    assert [i["symbol"] for i in client.get("/ideas", params={"limit": 1}).json()["items"]] == [
        "AAA"
    ]
    before = client.get("/ideas", params={"date": "2021-01-04"})  # nothing stored by then
    assert before.status_code == 200
    assert (before.json()["session"], before.json()["items"], before.json()["total"]) == (
        None, [], 0
    )  # fmt: skip
    assert client.get("/ideas", params={"user": "Bad User"}).status_code == 400
    assert client.get("/ideas", params={"limit": 0}).status_code == 422


def test_ideas_on_an_empty_store_is_an_empty_list_not_a_404(tmp_path: Path) -> None:
    """The real app before any screener has run: 200 with no session, never a 404."""
    store = store_over(MemoryBackend(), FileConfigStore(tmp_path), UserContext("local"))
    empty = TestClient(create_app(ApiSettings("memory://", "config"), store))
    response = empty.get("/ideas")
    assert response.status_code == 200
    body = response.json()
    assert (body["session"], body["items"], body["screeners"], body["total"]) == (None, [], [], 0)
