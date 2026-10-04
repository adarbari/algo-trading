from fastapi.testclient import TestClient


def test_screen_configs_with_latest_run(client: TestClient) -> None:
    configs = client.get("/screens").json()
    assert [c["config"]["config_id"] for c in configs] == ["short_premium_liquidity"]
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
    assert first["picks"][0]["tier"] == "T1"
    assert first["picks"][1]["columns"] == {"spread": 0.05}
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
    assert client.get("/ideas", params={"date": "2021-01-04"}).status_code == 404
    assert client.get("/ideas", params={"user": "Bad User"}).status_code == 400
    assert client.get("/ideas", params={"limit": 0}).status_code == 422
