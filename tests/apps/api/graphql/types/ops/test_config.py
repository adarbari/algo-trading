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
    ta = {"breakout", "pullback", "support_reversal", "exhaustion", "trend_continuation",
          "range_breakout", "failed_breakout", "oversold_reversal", "momentum_12_1",
          "size_small", "pead_small_cap", "eap_all", "eap_volume", "ivol_high", "max_ret_high",
          "amihud_illiquid", "beta_low", "earnings_date_early", "eight_k_adverse_items",
          "nt_late_filer", "tender_offer_filed", "sp500_deletion", "pre_earnings_runup",
          "earnings_gap_volume", "earnings_gap_only", "short_term_momentum_turnover",
          "momentum_own_trend", "momentum_pullback_entry", "momentum_volume_confirmed",
          "earnings_vwap_overhang",
          "cp_iv_spread", "cp_iv_spread_rise", "iv_smirk", "iv_change_call", "iv_change_ibkr",
          "option_stock_volume", "retail_option_attention", "lottery_max", "volume_shock",
          "volume_shock_no_news", "dividend_month", "mispricing_composite",
          "pre_earnings_reversal", "earnings_neutral_reversal",
          "residual_momentum",
          "volatility_scaled_momentum", "frog_in_the_pan", "momentum_x_quality_interaction",
          "fifty_two_week_high", "industry_momentum", "residual_reversal", "sector_reversal",
          "low_beta", "low_volatility",
          "cash_op_profitability", "composite_value", "qmj", "net_share_issuance", "asset_growth",
          "distress_ohlson", "bdc_price_to_nav",
          "vrp_cross_section", "iv_rank_high", "etf_flow_pressure",
          "insider_cluster_buys", "short_squeeze_dtc"}  # fmt: skip
    assert set(configs) == {"short_premium_liquidity", "sma_trend", "vrp_scanner", "vrp_iv_hv"} | ta
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
