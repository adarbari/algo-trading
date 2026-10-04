from fastapi.testclient import TestClient

TABLE = "/screens/vrp_scanner/table"
CLOSE = "rollup.price_stats@v2.close"


def test_the_review_table_with_criteria_changes_and_features(client: TestClient) -> None:
    body = client.get(TABLE, params={"columns": CLOSE, "sort": f"-{CLOSE}"}).json()
    assert (body["user"], body["session"], body["previous_session"]) == (
        "site",
        "2022-11-23",
        "2022-11-22",
    )
    assert body["decisions"] == {"QUALIFIED": 1, "WATCH": 1, "REJECT": 1}
    assert body["changes"] == {"new": 1, "dropped": 1}
    assert body["feature_columns"] == [CLOSE]
    rows = {r["symbol"]: r for r in body["page"]["items"]}
    assert rows["AAA"]["change"] == "new" and rows["CCC"]["change"] == "dropped"
    assert rows["AAA"]["criteria"]["iv30"] == {"value": 0.62, "outcome": "PASS"}
    assert rows["AAA"]["columns"] == {"spread": 0.05}
    assert CLOSE in rows["AAA"]["features"]


def test_filters_and_paging(client: TestClient) -> None:
    only = client.get(TABLE, params={"decision": "qualified,watch", "size": 1, "page": 2}).json()
    assert (only["page"]["total"], [r["symbol"] for r in only["page"]["items"]]) == (2, ["BBB"])
    assert client.get(TABLE, params={"change": "dropped"}).json()["page"]["total"] == 1
    assert client.get(TABLE, params={"q": "ccc"}).json()["page"]["total"] == 1


def test_bad_input_and_not_found(client: TestClient) -> None:
    assert client.get(TABLE, params={"sort": "nope"}).status_code == 400
    assert client.get(TABLE, params={"change": "gone"}).status_code == 400
    assert client.get(TABLE, params={"columns": "feature.no_such"}).status_code == 400
    assert client.get("/screens/nope/table").status_code == 404
    assert client.get("/screens/sma_trend/table").status_code == 404  # a strategy
    assert client.get("/screens/short_premium_liquidity/table").status_code == 404  # not rules
    assert client.get(TABLE, params={"date": "2021-01-04"}).status_code == 404
