"""The app factory: error mapping, CORS, authentication (ADR 0040: every route but the
health check resolves its caller once), OpenAPI export, the CLI and the latency budget."""

import re
import time
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from algotrade.config.site.settings import load_users
from algotrade.config.site.users import UserRecord
from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.configs.files import FileConfigStore
from algotrade_api import cli
from algotrade_api.auth.mode import AuthConfig, AuthMode, open_authenticator
from algotrade_api.auth.protocol import UnauthenticatedError
from algotrade_api.deps import DEV_ORIGINS, ApiSettings, ReadStore
from algotrade_api.main import create_app, openapi_json
from tests.apps.api.conftest import SUPABASE_URL, Tokens
from tests.helpers.api_store import as_user

REPO = Path(__file__).resolve().parents[3]


def test_committed_openapi_is_up_to_date() -> None:
    committed = (REPO / "apps" / "api" / "openapi.json").read_text()
    assert committed == openapi_json(), "run scripts/export_openapi.py and commit the result"


def test_openapi_is_served(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/health" in paths and "/chains/{underlying_id}/live" in paths
    assert not [p for p in paths if p.startswith("/admin")]  # Admin reads are GraphQL


def test_no_route_takes_a_user_query_parameter(client: TestClient) -> None:
    """``?user=`` retired (ADR 0040): writes act for the caller, an admin names another user in
    the ``X-Act-For`` header (a body field on the preview POSTs), never in the URL."""
    document = client.get("/openapi.json").json()
    named = [
        (path, method)
        for path, operations in document["paths"].items()
        for method, operation in operations.items()
        for p in operation.get("parameters", [])
        if p["name"] == "user" and p["in"] == "query"
    ]
    assert named == []
    draft = document["paths"]["/screeners/{screener_id}/draft"]["put"]
    assert any(p["name"] == "X-Act-For" and p["in"] == "header" for p in draft["parameters"])


def test_cors_allows_the_local_web_dev_server(client: TestClient) -> None:
    origin = DEV_ORIGINS[0]
    response = client.get("/health", headers={"Origin": origin})
    assert response.headers["access-control-allow-origin"] == origin
    other = client.get("/health", headers={"Origin": "https://example.com"})
    assert "access-control-allow-origin" not in other.headers


def test_cors_origins_come_from_the_environment(
    api_golden: tuple[ReadStore, dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ALGOTRADE_CORS_ORIGINS", raising=False)
    assert ApiSettings.from_env().cors_origins == DEV_ORIGINS
    monkeypatch.setenv("ALGOTRADE_CORS_ORIGINS", "https://app.example.com, https://b.example.com/")
    settings = ApiSettings.from_env()
    assert settings.cors_origins == ("https://app.example.com", "https://b.example.com")
    app = create_app(settings, api_golden[0], authenticator=as_user())
    http = TestClient(app)
    preflight = http.options(
        "/graphql",
        headers={
            "Origin": "https://app.example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert preflight.headers["access-control-allow-origin"] == "https://app.example.com"
    assert "authorization" in preflight.headers["access-control-allow-headers"]
    dev = http.get("/health", headers={"Origin": DEV_ORIGINS[0]})
    assert "access-control-allow-origin" not in dev.headers  # the list replaces the default


def test_configuration_errors_are_400(
    api_golden: tuple[ReadStore, dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: object) -> None:
        raise ConfigurationError("bad config")

    monkeypatch.setattr("algotrade.services.preview.screens.preview_screen", broken)
    app = create_app(ApiSettings("memory://", "config"), api_golden[0], authenticator=as_user())
    response = TestClient(app).post("/screeners/preview", json={"spec": {}})
    assert (response.status_code, response.json()) == (400, {"detail": "bad config"})


def test_settings_from_env_open_the_named_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ALGOTRADE_DATA_URL", f"file://{tmp_path}")
    monkeypatch.setenv("ALGOTRADE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("ALGOTRADE_USER", "alice")
    monkeypatch.setenv("ALGOTRADE_AUTH", "off")
    settings = ApiSettings.from_env()
    assert settings.auth.mode == "off"
    assert (settings.user, settings.config_dir) == ("alice", str(tmp_path))
    assert settings.debug is False  # GraphiQL only with ALGOTRADE_API_DEBUG=1
    body = TestClient(create_app(settings, authenticator=as_user())).get("/health").json()
    assert (body["storage"], body["latest_session"], body["tables"]) == ("file", None, [])


def test_cli_runs_uvicorn_on_localhost(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kw: calls.append((app, kw)))
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    cli.main(["--reload"])
    assert calls == [(cli.APP, {"host": "127.0.0.1", "port": 8000, "reload": True})]


def test_asgi_app_is_configured_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALGOTRADE_DATA_URL", "memory://")
    monkeypatch.setenv("ALGOTRADE_AUTH", "off")
    monkeypatch.delenv("ALGOTRADE_USER", raising=False)
    from algotrade_api import app  # noqa: PLC0415  (built at import, from the environment)

    assert app.app.state.store.kind == "memory"


def _supabase_app(
    api_golden: tuple[ReadStore, dict[str, str]], user_configs: Path, tokens: Tokens
) -> TestClient:
    """The app over the multi-user configs, verifying tokens of the test Supabase project
    against the registry those configs declare (users.toml + identity.toml)."""
    store = replace(api_golden[0], configs=FileConfigStore(user_configs))
    config = AuthConfig(AuthMode.SUPABASE, SUPABASE_URL)
    auth = open_authenticator(config, load_users(store.configs), "local", tokens.fetch())
    settings = ApiSettings("memory://", str(user_configs))
    return TestClient(create_app(settings, store, authenticator=auth))


@pytest.fixture(scope="module")
def signed(
    api_golden: tuple[ReadStore, dict[str, str]], user_configs: Path, tokens: Tokens
) -> TestClient:
    return _supabase_app(api_golden, user_configs, tokens)


SESSION = {"query": "{ session { date } }"}


def _as(tokens: Tokens, email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens.mint(email=email)}"}


def test_no_token_is_401_with_a_challenge_and_cors(signed: TestClient) -> None:
    origin = DEV_ORIGINS[0]
    response = signed.post("/graphql", json=SESSION, headers={"Origin": origin})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.headers["access-control-allow-origin"] == origin  # the browser can read it
    assert signed.post("/features/check", json={"expr": "1"}).status_code == 401
    assert signed.get("/health").status_code == 200  # the one public route


def test_a_token_for_nobody_in_the_registry_is_403(signed: TestClient, tokens: Tokens) -> None:
    response = signed.post("/graphql", json=SESSION, headers=_as(tokens, "eve@example.com"))
    assert response.status_code == 403 and "eve" not in response.text
    viewer = {"query": "{ viewer { id role workspaces } }"}
    me = signed.post("/graphql", json=viewer, headers=_as(tokens, "ana@example.com"))
    assert me.json() == {
        "data": {"viewer": {"id": "ana", "role": "admin", "workspaces": ["admin", "trader"]}}
    }


def test_graphql_over_websocket_is_not_served(signed: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect), signed.websocket_connect("/graphql"):
        pass  # no subscriptions: the only way in is a request the caller guard sees


def test_two_callers_on_one_app_read_their_own_configs(signed: TestClient, tokens: Tokens) -> None:
    # One app, one result cache: alice's sorted table (her user feature) must not leak to bob.
    query = """query($columns: [FeatureName!]!, $sort: String) {
      table(columns: $columns, sort: $sort) { instruments { symbol } rows } }"""
    variables = {"columns": ["feature.hv20_pct"], "sort": "-feature.hv20_pct"}
    body = {"query": query, "variables": variables}
    for _ in range(2):  # the second read of each comes from the cache
        alice = signed.post("/graphql", json=body, headers=_as(tokens, "alice@example.com"))
        mine = alice.json()["data"]["table"]
        assert mine["rows"][0][0] == pytest.approx(22.0)
        # carol's feature has alice's name and the opposite sign: the cached order is keyed on
        # the caller and their catalogue, never shared.
        carol = signed.post("/graphql", json=body, headers=_as(tokens, "carol@example.com"))
        theirs = carol.json()["data"]["table"]
        assert [i["symbol"] for i in mine["instruments"]] == ["BULL", "BBB", "AAA", "CCC"]
        assert [i["symbol"] for i in theirs["instruments"]] == ["AAA", "BBB", "BULL", "CCC"]
        bob = signed.post("/graphql", json=body, headers=_as(tokens, "BOB@example.com"))
        assert bob.json()["errors"][0]["extensions"]["code"] == "UNKNOWN_FEATURE"
    formula = {"expr": "hv20_pct / 100"}
    check = signed.post("/features/check", json=formula, headers=_as(tokens, "bob@example.com"))
    assert check.status_code == 400  # REST reads are the caller's too


def test_a_trader_cannot_act_for_another_user(signed: TestClient, tokens: Tokens) -> None:
    body = {"expr": "hv20_pct / 100", "user": "alice"}

    def status(email: str) -> int:
        return signed.post("/features/check", json=body, headers=_as(tokens, email)).status_code

    assert status("bob@example.com") == 403  # a trader naming someone else
    assert status("ana@example.com") == 200 and status("alice@example.com") == 200


class Refuse:
    """An authenticator that lets nobody in."""

    def authenticate(self, request: object) -> UserRecord:
        raise UnauthenticatedError("no")


def test_every_route_but_the_health_check_resolves_its_caller(
    api_golden: tuple[ReadStore, dict[str, str]],
) -> None:
    app = create_app(ApiSettings("memory://", "config"), api_golden[0], authenticator=Refuse())
    client = TestClient(app)
    paths = app.openapi()["paths"]
    assert "/graphql" in paths
    for path, operations in paths.items():
        url = re.sub(r"\{[^}]+\}", "x", path)
        for method in operations:
            status = client.request(method.upper(), url, json={}).status_code
            assert status == (200 if path == "/health" else 401), (method, path, status)


def test_the_caller_is_resolved_once_per_request(
    api_golden: tuple[ReadStore, dict[str, str]],
) -> None:
    stub = as_user()
    app = create_app(ApiSettings("memory://", "config"), api_golden[0], authenticator=stub)
    client = TestClient(app)
    query = {"query": "{ session { date } catalogue { name } }"}
    assert client.post("/graphql", json=query).status_code == 200
    assert stub.calls == 1  # the route's guard and the GraphQL context share it
    formula = {"expr": "price_stats.close > 10"}
    assert client.post("/features/check", json=formula).status_code == 200
    assert stub.calls == 2  # guard, Reads -> Context, and the route's own Caller: one call


def test_cli_refuses_auth_off_on_a_public_address(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kw: calls.append(kw["host"]))
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setenv("ALGOTRADE_AUTH", "off")
    with pytest.raises(SystemExit):
        cli.main(["--host", "0.0.0.0"])
    cli.main(["--host", "127.0.0.1"])
    monkeypatch.setenv("ALGOTRADE_AUTH", "supabase")
    cli.main(["--host", "0.0.0.0"])
    assert calls == ["127.0.0.1", "0.0.0.0"]


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
