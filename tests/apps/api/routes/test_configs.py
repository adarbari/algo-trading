from fastapi.testclient import TestClient


def test_config_list(client: TestClient) -> None:
    configs = {c["config_id"]: c for c in client.get("/configs").json()}
    assert set(configs) == {"short_premium_liquidity", "sma_trend"}
    assert configs["sma_trend"]["kind"] == "strategy"
    assert configs["sma_trend"]["selection"] == "liquid_optionable"
    assert len(configs["sma_trend"]["hash"]) == 64


def test_config_detail_resolves_layers(client: TestClient) -> None:
    body = client.get("/configs/sma_trend").json()
    assert body["user"] == "local"
    assert body["layers"] == ["site/strategies/sma_trend", "site/selections/liquid_optionable"]
    assert body["resolved"]["params"] == {"fast": 20, "slow": 100}
    assert body["resolved"]["settings"]["backtest"]["initial_cash"] == 100000.0


def test_unknown_config_is_404(client: TestClient) -> None:
    assert client.get("/configs/nope").status_code == 404
