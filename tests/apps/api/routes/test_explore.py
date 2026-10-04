from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

HV20 = "rollup.price_stats@v2.hv20"
CLOSE = "rollup.price_stats@v2.close"


def test_ticker_table_with_requested_columns(client: TestClient) -> None:
    params = {"columns": f"{HV20},instrument.sector,{HV20}", "sort": f"-{HV20}"}
    body = client.get("/explore/tickers", params=params).json()
    assert body["columns"] == [HV20, "instrument.sector"]
    rows = body["page"]["items"]
    assert [r["symbol"] for r in rows] == ["BULL", "BBB", "AAA", "CCC"]  # null hv20 last
    assert rows[2]["instrument.sector"] == "Technology"
    assert rows[0][HV20] == pytest.approx(0.22)
    assert set(rows[0]) == {"instrument_id", "symbol", "company_name", "security_type",
                            HV20, "instrument.sector"}  # fmt: skip


def test_ticker_table_with_expression_features(client: TestClient) -> None:
    params = {"columns": "feature.liquidity_class", "sort": "feature.liquidity_class"}
    rows = client.get("/explore/tickers", params=params).json()["page"]["items"]
    assert [(r["symbol"], r["feature.liquidity_class"]) for r in rows] == [
        ("AAA", "HIGH"), ("BULL", "HIGH"), ("CCC", "LOW"), ("BBB", "MEDIUM"),
    ]  # fmt: skip
    tiers = {"ids": "AAA,CCC", "features": "feature.option_tier"}
    compare = client.get("/explore/compare", params=tiers)
    assert compare.json()["rows"][0]["values"] == {"EQ:AAA": "A", "EQ:CCC": "D"}


def test_ticker_table_and_compare_take_the_users_features(
    user_client: Callable[[str], TestClient],
) -> None:
    params = {"columns": "feature.hv20_pct", "sort": "-feature.hv20_pct"}
    rows = user_client("alice").get("/explore/tickers", params=params).json()["page"]["items"]
    assert [(r["symbol"], r["feature.hv20_pct"]) for r in rows] == [
        ("BULL", pytest.approx(22.0)), ("BBB", pytest.approx(21.0)),
        ("AAA", pytest.approx(20.0)), ("CCC", None),
    ]  # fmt: skip
    compare = {"ids": "AAA", "features": "feature.hv20_pct"}
    body = user_client("alice").get("/explore/compare", params=compare).json()
    assert body["rows"][0]["values"]["EQ:AAA"] == pytest.approx(20.0)
    assert user_client("bob").get("/explore/tickers", params=params).status_code == 400
    assert user_client("bob").get("/explore/compare", params=compare).status_code == 400


def test_ticker_table_filters_pages_and_defaults(client: TestClient) -> None:
    body = client.get("/explore/tickers", params={"leveraged": "true"}).json()
    assert [r["symbol"] for r in body["page"]["items"]] == ["BULL"]
    assert (body["sort"], body["columns"]) == ("symbol", [])
    params = {"optionable": "false", "leveraged": "true"}
    assert client.get("/explore/tickers", params=params).json()["page"]["items"] == []
    paged = client.get("/explore/tickers", params={"size": 1, "page": 2}).json()
    assert [r["symbol"] for r in paged["page"]["items"]] == ["BBB"]


def test_ticker_table_rejects_unknown_columns_and_sort(client: TestClient) -> None:
    assert client.get("/explore/tickers", params={"columns": "rollup.x@v1.y"}).status_code == 400
    assert client.get("/explore/tickers", params={"sort": "nope"}).status_code == 400


def test_compare_features_one_row_per_feature(client: TestClient) -> None:
    params = {"ids": "AAA,EQ:BBB", "features": f"{CLOSE},instrument.security_type"}
    body = client.get("/explore/compare", params=params).json()
    assert [i["symbol"] for i in body["instruments"]] == ["AAA", "BBB"]
    rows = {r["feature"]: r for r in body["rows"]}
    assert rows[CLOSE]["values"] == {"EQ:AAA": 101.0, "EQ:BBB": 102.0}
    assert rows["instrument.security_type"]["dtype"] == "str"
    every = client.get("/explore/compare", params={"ids": "AAA"}).json()
    assert len(every["rows"]) > 50


def test_compare_validates_ids_and_features(client: TestClient) -> None:
    assert client.get("/explore/compare", params={"ids": "AAA,NOPE"}).status_code == 404
    too_many = ",".join(["AAA"] * 3 + [f"X{i}" for i in range(10)])
    assert client.get("/explore/compare", params={"ids": too_many}).status_code == 400
    bad = client.get("/explore/compare", params={"ids": "AAA", "features": "x.y"})
    assert bad.status_code == 400


def test_compare_prices_rebased_on_one_axis(client: TestClient) -> None:
    params = {"ids": "AAA,BBB", "from": "2022-11-01", "to": "2022-11-23"}
    body = client.get("/explore/compare/prices", params=params).json()
    assert body["rebase"] == 100.0
    assert body["dates"][0] == "2022-11-01" and body["dates"][-1] == "2022-11-23"
    for series in body["series"].values():
        assert series[0] == pytest.approx(100.0)
        assert len(series) == len(body["dates"])
    raw = client.get("/explore/compare/prices", params={**params, "rebase": 0}).json()
    assert raw["rebase"] is None
    assert raw["series"]["EQ:AAA"][0] != pytest.approx(100.0)


def test_compare_prices_without_bars_is_empty(client: TestClient) -> None:
    params = {"ids": "AAA", "from": "2010-01-01", "to": "2010-02-01"}
    body = client.get("/explore/compare/prices", params=params).json()
    assert (body["dates"], body["series"]) == ([], {"EQ:AAA": []})
