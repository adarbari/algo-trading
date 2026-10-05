"""The app factory: error mapping, CORS, OpenAPI export, the CLI and the latency budget."""

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from algotrade.core.model.errors import ConfigurationError
from algotrade.services.explore.store import ReadStore
from algotrade_api import cli
from algotrade_api.deps import DEV_ORIGINS, ApiSettings
from algotrade_api.main import create_app, openapi_json

REPO = Path(__file__).resolve().parents[3]


def test_committed_openapi_is_up_to_date() -> None:
    committed = (REPO / "apps" / "api" / "openapi.json").read_text()
    assert committed == openapi_json(), "run scripts/export_openapi.py and commit the result"


def test_openapi_is_served(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/universe" in paths and "/chains/{underlying_id}/live" in paths


def test_cors_allows_the_local_web_dev_server(client: TestClient) -> None:
    origin = DEV_ORIGINS[0]
    response = client.get("/health", headers={"Origin": origin})
    assert response.headers["access-control-allow-origin"] == origin
    other = client.get("/health", headers={"Origin": "https://example.com"})
    assert "access-control-allow-origin" not in other.headers


def test_configuration_errors_are_400(
    explore: tuple[ReadStore, dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: object) -> None:
        raise ConfigurationError("bad config")

    monkeypatch.setattr("algotrade.services.explore.configs.resolve_config", broken)
    app = create_app(ApiSettings("memory://", "config"), explore[0])
    response = TestClient(app).get("/configs/sma_trend")
    assert (response.status_code, response.json()) == (400, {"detail": "bad config"})


def test_settings_from_env_open_the_named_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ALGOTRADE_DATA_URL", f"file://{tmp_path}")
    monkeypatch.setenv("ALGOTRADE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("ALGOTRADE_USER", "alice")
    settings = ApiSettings.from_env()
    assert (settings.user, settings.config_dir) == ("alice", str(tmp_path))
    assert settings.debug is False  # GraphiQL only with ALGOTRADE_API_DEBUG=1
    body = TestClient(create_app(settings)).get("/health").json()
    assert (body["storage"], body["latest_session"], body["tables"]) == ("file", None, [])


def test_cli_runs_uvicorn_on_localhost(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kw: calls.append((app, kw)))
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    cli.main(["--reload"])
    assert calls == [(cli.APP, {"host": "127.0.0.1", "port": 8000, "reload": True})]


def test_asgi_app_is_configured_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALGOTRADE_DATA_URL", "memory://")
    from algotrade_api import app  # noqa: PLC0415  (built at import, from the environment)

    assert app.app.state.store.kind == "memory"


ENDPOINTS = (
    "/health",
    "/admin/runs/nightly",
    "/universe",
    "/admin/review/figi",
    "/admin/review/leveraged",
    "/chains/AAA/live?expiry=2022-12-23",
    "/features",
    "/features/rollup.price_stats@v2.hv20/distribution",
    "/screens",
    "/screens/short_premium_liquidity/results",
    "/screens/vrp_scanner/table?columns=rollup.price_stats@v2.hv20",
    "/backtests",
    "/configs",
    "/configs/sma_trend",
    "/explore/tickers?columns=rollup.price_stats@v2.hv20&sort=-rollup.price_stats@v2.hv20",
    "/explore/compare?ids=AAA,BBB",
    "/explore/compare/prices?ids=AAA,BBB",
    "/admin/ingestion/completeness",
    "/admin/ingestion/chains/option_quotes/2022-11-23",
    "/admin/quality",
    "/admin/verification/ibkr",
)


@pytest.mark.parametrize("path", ENDPOINTS)
def test_every_endpoint_answers_within_a_second_on_golden_data(
    client: TestClient, path: str
) -> None:
    # CPU time, not wall time: tests run in parallel (one worker per CPU), so waiting for a
    # CPU is noise, while a regression costs work every time. Best of three for the rest.
    timings = []
    for _ in range(3):
        started = time.process_time()
        response = client.get(path)
        timings.append(time.process_time() - started)
        assert response.status_code == 200, response.text
    assert min(timings) < 1.0, f"{path} took {min(timings):.2f}s (best of 3: {timings})"


# The pages' main GraphQL operations. InstrumentFacts: the Explore Overview pane; IdeasPage:
# the Ideas page (apps/web/src/entities/idea/api); the detail tabs' (read-model PR 6): events,
# bars, feature history, the option chain and one expiry's quotes, an ETF's holdings
# (apps/web/src/entities/{instrument,chain,holdings}/api).
INSTRUMENT_FACTS = """query InstrumentFacts($key: String!, $names: [FeatureName!]!) {
  session { date isLatest missing }
  instrument(key: $key) {
    instrumentId symbol name securityType exchange isEtf description referenceSnapshot
    features(names: $names) {
      name value unknown { code detail } info { format unit nullMeaning description }
    }
  }
}"""
OVERVIEW_NAMES = [
    "instrument.sector", "instrument.industry", "instrument.website", "instrument.in_sp500",
    "instrument.optionable", "instrument.is_leveraged", "instrument.is_inverse",
    "instrument.leverage", "instrument.tracks", "rollup.price_stats@v2.close",
    "feature.market_cap", "feature.pe_ratio", "rollup.financials@v1.revenue_ttm",
    "rollup.price_stats@v2.high_52w", "rollup.price_stats@v2.low_52w",
    "feature.pct_from_high_52w", "rollup.price_stats@v2.hv30", "rollup.iv30@v1.iv30",
    "feature.iv_rank", "feature.div_yield", "rollup.earnings@v1.next_earnings_date",
    "rollup.earnings@v1.last_earnings_date", "rollup.earnings@v1.days_to_earnings",
    "rollup.earnings@v1.earnings_time",
]  # fmt: skip
IDEAS_PAGE = """query IdeasPage($limit: Int!, $names: [FeatureName!]!) {
  ideas(limit: $limit) {
    session priority total
    screeners {
      screener { id name owner version } run { runId configVersion } notRun { code detail }
      picked top { instrumentId score instrument { symbol } }
    }
    items {
      rank instrumentId
      instrument {
        symbol
        features(names: $names) {
          name value unknown { code detail } info { format unit dtype nullMeaning }
        }
      }
      picks {
        configId decision score reasons flags criteria { id value } columns { name value }
      }
    }
  }
}"""
IDEA_NAMES = [
    "rollup.earnings@v1.next_earnings_date", "rollup.earnings@v1.last_earnings_date",
    "rollup.earnings@v1.days_to_earnings", "rollup.nearest_expiry@v1.dte",
    "feature.earnings_before_expiry", "feature.vrp_iv30",
]  # fmt: skip
DETAIL = {
    "InstrumentEvents": "query InstrumentEvents($key: String!) { instrument(key: $key) { "
    "instrumentId events { table kind date ts values } } }",
    "InstrumentPrices": "query InstrumentPrices($key: String!, $start: Date!) { instrument(key: "
    "$key) { instrumentId prices(start: $start) { start end bars { session close volume } } } }",
    "InstrumentHistory": "query InstrumentHistory($key: String!, $names: [FeatureName!]!, $start: "
    "Date!, $date: Date!) { instrument(key: $key, date: $date) { instrumentId series(names: "
    "$names, start: $start) { names points { session values } } } }",
    "OptionChain": "query OptionChain($key: String!, $names: [FeatureName!]!) { instrument(key: "
    "$key) { instrumentId symbol features(names: $names) { name value unknown { code detail } "
    "info { format unit dtype nullMeaning } } chain { underlyingId session status expiries { "
    "date days } strikes } } }",
    "OptionQuotes": "query OptionQuotes($key: String!, $expiry: Date!, $date: Date!) { "
    "instrument(key: $key, date: $date) { "
    "instrumentId chain { quotes(expiry: $expiry) { instrumentId expiry right strike bid ask "
    "last volume openInterest iv delta gamma theta vega } } } }",
    "EtfHoldings": "query EtfHoldings($key: String!, $top: Int!) { instrument(key: $key) { "
    "instrumentId isEtf holdings(top: $top) { asOf source total items { rank name symbol weight "
    "assetClass instrument { symbol } } } } }",
}
CHAIN_NAMES = [
    "rollup.option_liquidity@v1.target_expiry",
    "rollup.option_liquidity@v1.underlying_price",
    "rollup.iv30@v1.iv30",
]
HISTORY_NAMES = [n for n in OVERVIEW_NAMES if not n.startswith("instrument.") and "date" not in n]
OPERATIONS = {
    "InstrumentFacts": (INSTRUMENT_FACTS, {"key": "AAA", "names": OVERVIEW_NAMES}),
    "InstrumentEvents": (DETAIL["InstrumentEvents"], {"key": "AAA"}),
    "InstrumentPrices": (DETAIL["InstrumentPrices"], {"key": "AAA", "start": "2021-11-23"}),
    "InstrumentHistory": (
        DETAIL["InstrumentHistory"],
        {"key": "AAA", "names": HISTORY_NAMES, "start": "2022-08-25", "date": "2022-11-23"},
    ),
    "OptionChain": (DETAIL["OptionChain"], {"key": "AAA", "names": CHAIN_NAMES}),
    "OptionQuotes": (
        DETAIL["OptionQuotes"],
        {"key": "AAA", "expiry": "2022-12-23", "date": "2022-11-23"},
    ),
    "EtfHoldings": (DETAIL["EtfHoldings"], {"key": "BULL", "top": 10}),
    "IdeasPage": (IDEAS_PAGE, {"limit": 200, "names": IDEA_NAMES}),
}


@pytest.mark.parametrize("name", OPERATIONS)
def test_every_page_operation_answers_within_a_second_on_golden_data(
    client: TestClient, name: str
) -> None:
    query, variables = OPERATIONS[name]
    timings = []
    for _ in range(3):  # CPU time, best of three (as above)
        started = time.process_time()
        response = client.post("/graphql", json={"query": query, "variables": variables})
        timings.append(time.process_time() - started)
        assert response.status_code == 200 and "errors" not in response.json(), response.text
    assert min(timings) < 1.0, f"{name} took {min(timings):.2f}s (best of 3: {timings})"
