"""The event edges and avoid lists of EB E3: each short-side edge's screener orders so the
harness's short leg (the lowest scores) takes the most liquid names first, a long event edge's
screener ranks best first, every non-blocked event edge declares a field the harness reads, and a
blocked one says what is missing."""

import tomllib
from datetime import date

import pytest

from algotrade.config.edges.chain import tenor_sessions
from algotrade.config.edges.document import CLOSED, MODEL_KIND, Edge
from algotrade.config.edges.loading import load_edges
from algotrade.config.strategy.schema import Selection
from algotrade.config.user import UserContext
from algotrade.core.model.predicates import Group
from algotrade.core.views.feature_view import FeatureView
from algotrade.engines.selection.evaluate import evaluate_selection
from algotrade.services.configs import resolve_config
from algotrade.services.evaluation.cross_section.measuring import MIN_SCORE_COVERAGE
from algotrade.storage.configs.files import FileConfigStore
from algotrade.strategies.screeners import Decision
from algotrade.strategies.screeners.rules import evaluate_screen
from tests.conftest import REPO_ROOT

STORE = FileConfigStore(REPO_ROOT / "config", local=False)
E3 = (
    "earnings_date_shift", "eight_k_item_drift", "late_filer_nt_drift", "tender_offer_drift",
    "sp500_deletions_long", "pre_earnings_runup_winners", "earnings_gap_volume_drift",
    "spinoff_drift", "reverse_split_distress_filter", "thematic_etf_launch_fade",
)  # fmt: skip
EDGES = {e.id: e for e in load_edges(STORE) if e.id in E3}
ADV = "rollup.price_stats@v2.adv_usd_20d"


def _rank(screener: str) -> tuple[str, str]:
    path = REPO_ROOT / f"config/site/presets/screeners/{screener}/v1.toml"
    rank = tomllib.loads(path.read_text())["rank"]
    return rank["tie_break"], rank["tie_break_order"]


def test_every_e3_document_is_filed() -> None:
    assert set(EDGES) == set(E3)


@pytest.mark.parametrize("edge", [e for e in EDGES.values() if e.outcome.side == "short"])
def test_a_short_edge_shorts_the_most_liquid_names_first(edge: Edge) -> None:
    """The short leg is the lowest scores (cross_section/measuring.py ``_side_picks``): the score
    is the negative of the dollar volume, so the order is ascending (a wrong direction would
    short the least liquid, the names an individual cannot borrow)."""
    assert edge.top_k is not None
    for screener in edge.screeners:
        assert _rank(screener) == (ADV, "asc"), screener


@pytest.mark.parametrize(
    "edge", [e for e in EDGES.values() if e.outcome.side == "long" and e.status not in CLOSED]
)
def test_a_long_event_edge_is_a_candidate_on_a_liquid_event_universe(edge: Edge) -> None:
    assert edge.status == "candidate" and edge.event_class is not None
    assert str(edge.frozen_from) == "2026-04-01" and edge.family
    where = edge.universe.where.rules()  # type: ignore[union-attr]
    assert any(r.field == ADV and r.op == "gte" for r in where), "a liquidity floor"


@pytest.mark.parametrize("edge", [e for e in EDGES.values() if e.status in CLOSED])
def test_a_blocked_edge_names_what_is_missing(edge: Edge) -> None:
    assert edge.status == "blocked" and not edge.screeners
    assert "EVENT_CLASSES" in edge.rejection_reason


# ---- EB E4: option P&L, closed-end fund and ETF flow edges
E4_OPTION = (
    "c12_vrp_cross_section_iv_hv", "c13_iv_term_structure_straddles",
    "c14_delta_hedged_characteristics", "c16_pre_earnings_straddle_buy",
    "c17_earnings_iv_crush_sell", "c18_iv_rank_conditional_selling",
)  # fmt: skip
E4_FUNDS = ("closed_end_fund_discounts", "cef_distribution_trap", "etf_flow_pressure")
E4 = (*E4_OPTION, *E4_FUNDS)
E4_EDGES = {e.id: e for e in load_edges(STORE) if e.id in E4}
BLOCKED = {
    "c13_iv_term_structure_straddles": "no history",
    "c16_pre_earnings_straddle_buy": "tenor_sessions",
    "c17_earnings_iv_crush_sell": "tenor_sessions",
    "closed_end_fund_discounts": "covered universe",
    "cef_distribution_trap": "covered universe",
}  # the keyword each blocked document's reason names


def test_every_e4_document_is_filed() -> None:
    assert set(E4_EDGES) == set(E4)


@pytest.mark.parametrize("edge", E4_EDGES.values(), ids=E4_EDGES)
def test_an_e4_edge_is_a_candidate_or_a_blocked_one_with_its_reason(edge: Edge) -> None:
    assert str(edge.frozen_from) == "2026-04-01" and edge.family
    if edge.id in BLOCKED:
        assert edge.status == "blocked" and BLOCKED[edge.id] in edge.rejection_reason
    else:
        assert edge.status == "candidate" and edge.screeners


@pytest.mark.parametrize("edge", [E4_EDGES[i] for i in E4_OPTION], ids=E4_OPTION)
def test_an_option_edge_is_a_model_pnl_whose_notes_say_so(edge: Edge) -> None:
    """Basis model (owner decision O3: no historical chains): the document names the model, its
    assumptions and the real-chain P&L (H13) that replaces it; the IV is IBKR's 30-day one."""
    assert edge.outcome.kind == MODEL_KIND and edge.outcome.basis == "model"
    assert "model, not a quote" in edge.notes and "H13" in edge.notes
    assert edge.outcome.iv_field == "rollup.ibkr_iv@v1.iv30_ibkr"
    assert edge.outcome.benchmark == "none" and edge.outcome.cost_bps


@pytest.mark.parametrize(
    "edge", [E4_EDGES[i] for i in E4_OPTION if i not in BLOCKED], ids=lambda e: e
)
def test_a_candidate_option_horizon_is_priced_by_its_30_day_vol(edge: Edge) -> None:
    tenor = tenor_sessions(edge.outcome.iv_field or "")
    assert tenor is not None
    assert all(tenor // 2 <= h <= tenor * 2 for h in edge.outcome.horizon_sessions)


@pytest.mark.parametrize("edge", E4_EDGES.values(), ids=E4_EDGES)
def test_no_two_group_or_unverified_figure_is_published(edge: Edge) -> None:
    """The sources' figures are decile spreads, long-short quintiles or one-leg premium averages,
    none of what the harness reports for the picks alone."""
    assert edge.published is None


def test_a_blocked_event_straddle_says_what_its_placeholder_horizon_is() -> None:
    for edge_id in ("c16_pre_earnings_straddle_buy", "c17_earnings_iv_crush_sell"):
        edge = E4_EDGES[edge_id]
        assert edge.status in CLOSED and not edge.screeners
        assert "placeholder" in edge.rejection_reason


def test_the_ranking_edges_compare_with_every_liquid_optionable_name() -> None:
    """A rank or gate over the optionable universe is read against selling on all of it: the
    plain schedules' base is the universe, and the gated edge keeps every qualified name."""
    for edge_id in ("c12_vrp_cross_section_iv_hv", "c14_delta_hedged_characteristics"):
        assert E4_EDGES[edge_id].base == "universe" and E4_EDGES[edge_id].top_k == 20
    c18 = E4_EDGES["c18_iv_rank_conditional_selling"]
    assert c18.base == "universe" and c18.top_k is None and c18.schedule == "every_session"


def test_the_etf_flow_screener_orders_so_the_heaviest_creation_is_shorted_first() -> None:
    """The short leg is the lowest scores (cross_section/measuring.py ``_side_picks``): an
    ascending order on the change scores a creation low."""
    edge = E4_EDGES["etf_flow_pressure"]
    assert edge.outcome.side == "short" and edge.top_k == 10
    path = REPO_ROOT / "config/site/presets/screeners/etf_flow_pressure/v1.toml"
    rank = tomllib.loads(path.read_text())["rank"]
    assert rank == {
        "tie_break": "rollup.etf_flows@v1.etf_shares_chg_21d",
        "tie_break_order": "asc",
    }
    variants = {v.id: v.outcome.side for v in edge.variants}
    assert variants == {"long_redemptions": "long", "long_short": "long_short"}


def test_the_etf_flow_base_is_the_funds_that_carry_a_score() -> None:
    """The harness ranks a short leg only when 80% of the base is scored (MIN_SCORE_COVERAGE);
    only iShares funds have a count, so the base must be those funds, not every liquid ETF."""
    edge = E4_EDGES["etf_flow_pressure"]
    spec = resolve_config(STORE, "etf_flow_pressure", UserContext("site")).screen_spec
    value = {"eq": lambda v: v, "gt": lambda v: v + 1, "gte": lambda v: v, "in": lambda v: v[0]}
    row = {r.field: value[r.op](r.value) for r in edge.universe.where.rules()}  # type: ignore[union-attr]
    row.update({c.rule.field: value[c.rule.op](c.rule.value) for c in spec.criteria})
    no_count = {k: v for k, v in row.items() if "etf_flows" not in k}
    names = {f"EQ:ISH{i}": row for i in range(4)} | {f"EQ:OTHER{i}": no_count for i in range(12)}
    view = FeatureView(date(2026, 11, 20), names)
    eligible = set(evaluate_selection(edge.universe, view).instruments)  # type: ignore[arg-type]
    scored = {
        r.instrument_id
        for r in evaluate_screen(spec, view).rows
        if r.decision is Decision.QUALIFIED
    }
    assert eligible == {f"EQ:ISH{i}" for i in range(4)}
    assert len(eligible & scored) >= MIN_SCORE_COVERAGE * len(eligible)
    where = edge.universe.where  # type: ignore[union-attr]
    loose = Selection(
        "loose", Group("all", tuple(r for r in where.rules() if "etf_flows" not in r.field))
    )
    base = set(evaluate_selection(loose, view).instruments)  # without the rule: 16 names, 4 scored
    assert len(base & scored) < MIN_SCORE_COVERAGE * len(base)


SPARSE = (
    "insider_opportunistic_cluster_buys", "short_squeeze_days_to_cover",
    "analyst_revision_momentum", "target_price_implied_return", "dual_class_spread_reversion",
)  # fmt: skip


@pytest.mark.parametrize("edge_id", SPARSE)
def test_a_sparse_score_edge_gates_its_universe_on_the_score(edge_id: str) -> None:
    """EB E6: the screener's score exists only for some names (a feature with rows for names with
    an event), and the harness calls a session too thin to rank when under 80 percent of the base
    is scored (a short leg is then not measured): the universe requires the score."""
    edge = {e.id: e for e in load_edges(STORE)}[edge_id]
    assert edge.base == "universe" and len(edge.screeners) == 1
    path = REPO_ROOT / f"config/site/presets/screeners/{edge.screeners[0]}/v1.toml"
    field = tomllib.loads(path.read_text())["rank"]["tie_break"]
    gated = [r for r in edge.universe.where.rules() if r.field == field]  # type: ignore[union-attr]
    assert gated and gated[0].op == "gte", f"{edge_id}: gate the universe on {field}"


def test_the_stock_leftover_edges_rank_the_short_leg_and_gate_the_universe() -> None:
    """EB E3b: ivol_avoid and lottery_max rank the jumpiest name last (the short leg takes the worst
    scores) and the avoid-list universe requires both scores; the news-conditioned
    reversal's main universe has no news gate (the baseline would pick the same names), only its
    short variants."""
    edges = {e.id: e for e in load_edges(STORE)}
    avoid = edges["idiosyncratic_volatility_and_max"]
    assert avoid.outcome.side == "short" and avoid.base == "universe"
    gated = {r.field for r in avoid.universe.where.rules()}  # type: ignore[union-attr]
    for screener in avoid.screeners:
        field, order = _rank(screener)
        assert order == "asc" and field in gated, screener
    news = edges["news_conditioned_reversal"]
    assert _rank(news.screeners[0])[1] == "asc"
    gate = (
        "feature.news_free_5d"  # not in the main universe: the baseline would pick the same names
    )
    assert gate not in {r.field for r in news.universe.where.rules()}  # type: ignore[union-attr]
    for v in news.variants:  # a short leg ranks by score over every pickable name: gate it there
        assert gate in {r.field for r in v.universe.where.rules()}  # type: ignore[union-attr]


# ---- EB H14 batch X: the documents the H4 classes, triggers and windows unblocked
BATCH_X = {
    "reverse_split_distress_filter": "on_event:reverse_split",
    "vix_mean_reversion_entry": "on_market:vix_spike",
    "treasury_month_end_extension": "calendar:pre_month_end",
    "december_losers_reversal": "calendar:year_turn",
}
BLOCKED_X = ("ipo_lockup_expiry", "tdf_contrarian_flows")


def test_batch_x_candidates_read_the_class_trigger_or_window_they_were_built_for() -> None:
    edges = {e.id: e for e in load_edges(STORE)}
    for edge_id, schedule in BATCH_X.items():
        edge = edges[edge_id]
        assert edge.status == "candidate" and edge.schedule == schedule, edge_id
        assert str(edge.frozen_from) == "2026-04-01" and edge.mechanism_kind, edge_id
    for edge_id in BLOCKED_X:
        assert edges[edge_id].status == "blocked" and edges[edge_id].rejection_reason, edge_id


def test_the_reverse_split_edge_is_a_liquid_short_with_the_whole_universe_as_its_base() -> None:
    """Short on liquid names only (O1, O2); the flagged names are the picks and every eligible name
    the base, so the lift does not read the picks against themselves (``names_for``)."""
    edge = {e.id: e for e in load_edges(STORE)}["reverse_split_distress_filter"]
    assert edge.outcome.side == "short" and edge.base == "universe" and edge.picks == "event"
    assert _rank(edge.screeners[0]) == (ADV, "asc")
    where = edge.universe.where.rules()  # type: ignore[union-attr]
    assert any(r.field == ADV and r.op == "gte" for r in where)


def test_the_december_losers_screen_gates_on_the_flag_and_ranks_the_biggest_loser_first() -> None:
    edge = {e.id: e for e in load_edges(STORE)}["december_losers_reversal"]
    path = REPO_ROOT / f"config/site/presets/screeners/{edge.screeners[0]}/v1.toml"
    doc = tomllib.loads(path.read_text())
    assert doc["criteria"]["loser"] == {
        "field": "feature.december_loser_flag", "op": "eq", "value": True,
    }  # fmt: skip
    assert doc["rank"]["tie_break"] == "rollup.trend_stats@v2.ret_252d"
    assert doc["rank"]["tie_break_order"] == "asc"  # the long leg takes the best score first
    assert edge.outcome.side == "long" and edge.base == "universe" and edge.top_k == 50


def test_the_time_series_documents_name_their_instruments_and_one_horizon() -> None:
    edges = {e.id: e for e in load_edges(STORE)}
    named = {
        "vix_mean_reversion_entry": (["SPY"], (63,)),
        "treasury_month_end_extension": (["TLT", "IEF", "AGG"], (3,)),
    }
    for edge_id, (symbols, horizons) in named.items():
        edge = edges[edge_id]
        assert edge.base == "out_of_window" and edge.outcome.benchmark == "none"
        assert edge.outcome.horizon_sessions == horizons
        assert next(r.value for r in edge.universe.where.rules()) == tuple(symbols)  # type: ignore[union-attr]
