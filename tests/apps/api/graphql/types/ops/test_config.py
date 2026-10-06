"""``Query.configs`` over the golden API store: every config the user sees (site presets,
then their own), resolved with its hash, or why it does not resolve; ``kind`` filters."""

from fastapi.testclient import TestClient

from algotrade.storage.backends.memory import MemoryBackend
from algotrade_api.deps import ApiSettings, ReadStore
from algotrade_api.main import create_app
from tests.apps.api.graphql.conftest import Graph
from tests.helpers.api_store import as_user, store_over

CONFIGS = """query C($kind: String) {
  configs(kind: $kind) { configId scope kind impl selection hash error }
}"""


def test_config_list(graph: Graph) -> None:
    body = graph(CONFIGS)
    assert "errors" not in body
    configs = {c["configId"]: c for c in body["data"]["configs"]}
    assert set(configs) == {"short_premium_liquidity", "sma_trend", "vrp_scanner"}
    assert (configs["sma_trend"]["kind"], configs["sma_trend"]["scope"]) == ("strategy", "site")
    assert configs["sma_trend"]["selection"] == "liquid_optionable"
    assert len(configs["sma_trend"]["hash"]) == 64 and configs["sma_trend"]["error"] is None


def test_kind_filters(graph: Graph) -> None:
    screeners = graph(CONFIGS, {"kind": "screener"})["data"]["configs"]
    assert screeners and {c["kind"] for c in screeners} == {"screener"}
    assert graph(CONFIGS, {"kind": "nothing"})["data"]["configs"] == []


def test_configs_answer_on_a_store_with_no_market_data(
    api_golden: tuple[ReadStore, dict[str, str]],
) -> None:
    """Configs are not session data: a fresh store still lists them (and the user's drafts)."""
    store = api_golden[0]
    empty = store_over(MemoryBackend(), store.configs, store.user)
    client = TestClient(
        create_app(ApiSettings("memory://", "config"), empty, authenticator=as_user())
    )
    query = "{ session { date } configs { configId } myScreens { screenerId } backtests { runId } }"
    body = client.post("/graphql", json={"query": query}).json()
    assert "errors" not in body, body
    data = body["data"]
    assert data["session"] is None and data["backtests"] == [] and data["myScreens"] == []
    assert {c["configId"] for c in data["configs"]} >= {"sma_trend", "vrp_scanner"}
