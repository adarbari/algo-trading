from fastapi.testclient import TestClient


def test_backtest_list(client: TestClient, ids: dict[str, str]) -> None:
    runs = client.get("/backtests").json()
    assert [r["run_id"] for r in runs] == [ids["backtest"]]
    assert runs[0]["metrics"] == {"sharpe": 1.2}
    assert (runs[0]["config_id"], runs[0]["user"], runs[0]["end"]) == (
        "sma_trend",
        "local",
        "2022-11-23",
    )


def test_backtest_detail(client: TestClient, ids: dict[str, str]) -> None:
    body = client.get(f"/backtests/{ids['backtest']}").json()
    assert [p["equity"] for p in body["equity"]] == [100000.0, 101000.0]
    assert body["fills"][0]["instrument_id"] == "EQ:AAA"
    assert body["selection"] == {"instruments": ["EQ:AAA"]}


def test_backtest_detail_not_found(client: TestClient, ids: dict[str, str]) -> None:
    assert client.get("/backtests/nope").status_code == 404
    assert client.get(f"/backtests/{ids['nightly']}").status_code == 404  # not a backtest
    assert client.get("/backtests/.x").status_code == 404
