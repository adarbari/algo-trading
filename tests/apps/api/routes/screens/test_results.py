from fastapi.testclient import TestClient


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
