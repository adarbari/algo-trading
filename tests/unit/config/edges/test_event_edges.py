"""The event edges and avoid lists of EB E3: each short-side edge's screener orders so the
harness's short leg (the lowest scores) takes the most liquid names first, a long event edge's
screener ranks best first, every non-blocked event edge declares a field the harness reads, and a
blocked one says what is missing."""

import tomllib

import pytest

from algotrade.config.edges.chain import tenor_sessions
from algotrade.config.edges.document import CLOSED, MODEL_KIND, Edge
from algotrade.config.edges.loading import load_edges
from algotrade.storage.configs.files import FileConfigStore
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
