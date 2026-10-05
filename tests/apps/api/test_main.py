"""The app factory: error mapping, CORS, OpenAPI export, the CLI and the latency budget."""

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from algotrade.core.model.errors import ConfigurationError
from algotrade_api import cli
from algotrade_api.deps import DEV_ORIGINS, ApiSettings, ReadStore
from algotrade_api.main import create_app, openapi_json

REPO = Path(__file__).resolve().parents[3]


def test_committed_openapi_is_up_to_date() -> None:
    committed = (REPO / "apps" / "api" / "openapi.json").read_text()
    assert committed == openapi_json(), "run scripts/export_openapi.py and commit the result"


def test_openapi_is_served(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/health" in paths and "/chains/{underlying_id}/live" in paths
    assert not [p for p in paths if p.startswith("/admin")]  # Admin reads are GraphQL


def test_cors_allows_the_local_web_dev_server(client: TestClient) -> None:
    origin = DEV_ORIGINS[0]
    response = client.get("/health", headers={"Origin": origin})
    assert response.headers["access-control-allow-origin"] == origin
    other = client.get("/health", headers={"Origin": "https://example.com"})
    assert "access-control-allow-origin" not in other.headers


def test_configuration_errors_are_400(
    api_golden: tuple[ReadStore, dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: object) -> None:
        raise ConfigurationError("bad config")

    monkeypatch.setattr("algotrade.services.preview.screens.preview_screen", broken)
    app = create_app(ApiSettings("memory://", "config"), api_golden[0])
    response = TestClient(app).post("/screeners/preview", json={"spec": {}})
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
    "/chains/AAA/live?expiry=2022-12-23",
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
# (apps/web/src/entities/{instrument,chain,holdings}/api); the feature table (read-model PR 7:
# the Explore ticker table and the compare set side by side) and the compare chart's prices
# (apps/web/src/entities/{feature,explore}/api).
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
FEATURE_TABLE = """query FeatureTable($columns: [FeatureName!]!, $keys: [String!],
  $securityType: String, $sector: String, $liquidityClass: String, $leveraged: Boolean,
  $optionable: Boolean, $q: String, $sort: String, $page: Int, $size: Int) {
  table(columns: $columns, keys: $keys, securityType: $securityType, sector: $sector,
        liquidityClass: $liquidityClass, leveraged: $leveraged, optionable: $optionable,
        q: $q, sort: $sort, page: $page, size: $size) {
    session { date missing } universeSnapshot preSnapshot sort total page size
    columns { name description format unit dtype nullMeaning licence scope }
    instruments { instrumentId symbol name }
    rows unknown
  }
}"""
COMPARE_PRICES = """query ComparePrices($keys: [String!]!, $start: Date!) {
  table(columns: [], keys: $keys) {
    instruments { instrumentId symbol prices(start: $start) { bars { session close } } }
  }
}"""
EXPLORE_COLUMNS = [
    "rollup.price_stats@v2.close", "rollup.iv30@v1.iv30", "feature.iv_hv_ratio",
    "feature.pct_from_high_52w", "rollup.earnings@v1.days_to_earnings",
]  # fmt: skip
CHAIN_NAMES = [
    "rollup.option_liquidity@v1.target_expiry",
    "rollup.option_liquidity@v1.underlying_price",
    "rollup.iv30@v1.iv30",
]
HISTORY_NAMES = [n for n in OVERVIEW_NAMES if not n.startswith("instrument.") and "date" not in n]
# A screener's results (read-model PR 8: apps/web/src/entities/screen/api/results.ts), sorted
# on a catalogue column over the whole run.
SCREENER_RESULTS = """query ScreenerResults($id: String!, $decisions: [String!], $change: String,
  $q: String, $sort: String, $columns: [FeatureName!], $page: Int, $size: Int) {
  session { date missing }
  screener(id: $id) {
    id name criteria { id field mode } displayColumns { name field }
    notRun { code detail }
    latestRun {
      runId session previousSession decisions { decision count } changes { change count }
      results(decisions: $decisions, change: $change, q: $q, sort: $sort, columns: $columns,
              page: $page, size: $size) {
        sort total page size missing
        columns { name description format unit dtype nullMeaning licence scope }
        rows unknown
        results {
          instrumentId rank decision score reasons flags change previousDecision
          instrument { instrumentId symbol name }
          criteria { id field mode outcome value distance }
          columns { name value }
        }
      }
    }
  }
}"""
# The Builder's and pickers' reads (read-model PR 9): the catalogue, one distribution, the
# saved backtests.
CATALOGUE = "query FeatureCatalogue { catalogue { name dtype format unit scope licence } }"
DISTRIBUTION = """query FeatureDistribution($name: FeatureName!) {
  distribution(name: $name) { count nulls quantiles { q value } histogram { lo hi count } }
}"""
BACKTESTS = "query Backtests { backtests { runId configId status metrics } }"
# The Admin Ingestion page's reads (read-model PR 10; apps/web/src/entities/{ingestion,run,
# verification,review}/api): the completeness grid, one cell, the session's quality checks and
# verification, the nightly runs, one run record and its items, the review lists.
RUN_FIELDS = "runId job session status startedAt durationS itemsTotal itemsByStatus stats"
ADMIN = {
    "IngestionCompleteness": "query IngestionCompleteness($sessions: Int!) { completeness("
    "sessions: $sessions) { sessions datasets lastClosed cells { dataset session status present "
    "expected basis runIds } } }",
    "IngestionCell": "query IngestionCell($dataset: String!, $date: Date!) { ingestionCell("
    "dataset: $dataset, date: $date) { job cell { status present expected } groups { reason "
    f"count examples }} runs {{ {RUN_FIELDS} }} }} }}",
    "QualityChecks": "query QualityChecks { quality { session runId status checks { name status "
    "detail } unknown { code } } }",
    "Verification": "query Verification { verification { session runIds instruments counts "
    "byCheck { check counts } failing unknown { code } } }",
    "NightlyRuns": "query NightlyRuns($limit: Int!) { nightlyRuns(limit: $limit) { runId session "
    "status durationS problems steps { name status durationS } } }",
    "RunRecord": f"query RunRecord($runId: String!) {{ run(runId: $runId) {{ {RUN_FIELDS} "
    "failures { reason count examples statuses } } runItems(runId: $runId) { key code status } }",
    "Review": "query Review { figiReview { session source items } leverageReview { session "
    "source items } }",
}
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
    "FeatureCatalogue": (CATALOGUE, {}),
    "FeatureDistribution": (DISTRIBUTION, {"name": "rollup.price_stats@v2.hv20"}),
    "Backtests": (BACKTESTS, {}),
    "IngestionCompleteness": (ADMIN["IngestionCompleteness"], {"sessions": 10}),
    "IngestionCell": (
        ADMIN["IngestionCell"],
        {"dataset": "chains/option_quotes", "date": "2022-11-23"},
    ),
    "QualityChecks": (ADMIN["QualityChecks"], {}),
    "Verification": (ADMIN["Verification"], {}),
    "NightlyRuns": (ADMIN["NightlyRuns"], {"limit": 10}),
    "RunRecord": (ADMIN["RunRecord"], {"runId": "nightly-2022-11-23"}),
    "Review": (ADMIN["Review"], {}),
    "Table": (
        FEATURE_TABLE,
        {"columns": EXPLORE_COLUMNS, "sort": "-feature.iv_hv_ratio", "page": 1, "size": 100},
    ),
    "CompareTable": (FEATURE_TABLE, {"columns": OVERVIEW_NAMES[9:], "keys": ["AAA", "BULL"]}),
    "ComparePrices": (COMPARE_PRICES, {"keys": ["AAA", "BULL"], "start": "2021-11-23"}),
    "ScreenerResults": (
        SCREENER_RESULTS,
        {
            "id": "vrp_scanner",
            "columns": EXPLORE_COLUMNS,
            "sort": "-feature.iv_hv_ratio",
            "size": 1000,
        },
    ),
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
