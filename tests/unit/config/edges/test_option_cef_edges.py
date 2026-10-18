"""The option P&L, closed-end fund and ETF flow edges of EB E4: every option edge is a model P&L
with its basis stated in the notes, a candidate reads only history that exists, a blocked one names
what is missing, no two-group figure is filed as published, and the short-side screener orders so
the harness's short leg (the lowest scores) takes the heaviest creations."""

import tomllib

import pytest

from algotrade.config.edges.document import CLOSED, MODEL_KIND, Edge
from algotrade.config.edges.loading import load_edges
from algotrade.config.edges.model_tenor import tenor_sessions
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT

STORE = FileConfigStore(REPO_ROOT / "config", local=False)
OPTION = (
    "c12_vrp_cross_section_iv_hv", "c13_iv_term_structure_straddles",
    "c14_delta_hedged_characteristics", "c16_pre_earnings_straddle_buy",
    "c17_earnings_iv_crush_sell", "c18_iv_rank_conditional_selling",
)  # fmt: skip
FUNDS = ("closed_end_fund_discounts", "cef_distribution_trap", "etf_flow_pressure")
E4 = (*OPTION, *FUNDS)
EDGES = {e.id: e for e in load_edges(STORE) if e.id in E4}
BLOCKED = {
    "c13_iv_term_structure_straddles": "no history",
    "c16_pre_earnings_straddle_buy": "tenor_sessions",
    "c17_earnings_iv_crush_sell": "tenor_sessions",
    "closed_end_fund_discounts": "covered universe",
    "cef_distribution_trap": "covered universe",
}  # the keyword each blocked document's reason names


def test_every_e4_document_is_filed() -> None:
    assert set(EDGES) == set(E4)


@pytest.mark.parametrize("edge", EDGES.values(), ids=EDGES)
def test_an_e4_edge_is_a_candidate_or_a_blocked_one_with_its_reason(edge: Edge) -> None:
    assert str(edge.frozen_from) == "2026-04-01" and edge.family
    if edge.id in BLOCKED:
        assert edge.status == "blocked" and BLOCKED[edge.id] in edge.rejection_reason
    else:
        assert edge.status == "candidate" and edge.screeners


@pytest.mark.parametrize("edge", [EDGES[i] for i in OPTION], ids=OPTION)
def test_an_option_edge_is_a_model_pnl_whose_notes_say_so(edge: Edge) -> None:
    """Basis model (owner decision O3: no historical chains): the document names the model, its
    assumptions and the real-chain P&L (H13) that replaces it; the IV is IBKR's 30-day one."""
    assert edge.outcome.kind == MODEL_KIND and edge.outcome.basis == "model"
    assert "model, not a quote" in edge.notes and "H13" in edge.notes
    assert edge.outcome.iv_field == "rollup.ibkr_iv@v1.iv30_ibkr"
    assert edge.outcome.benchmark == "none" and edge.outcome.cost_bps


@pytest.mark.parametrize("edge", [EDGES[i] for i in OPTION if i not in BLOCKED], ids=lambda e: e)
def test_a_candidate_option_horizon_is_priced_by_its_30_day_vol(edge: Edge) -> None:
    tenor = tenor_sessions(edge.outcome.iv_field or "")
    assert tenor is not None
    assert all(tenor // 2 <= h <= tenor * 2 for h in edge.outcome.horizon_sessions)


@pytest.mark.parametrize("edge", EDGES.values(), ids=EDGES)
def test_no_two_group_or_unverified_figure_is_published(edge: Edge) -> None:
    """The sources' figures are decile spreads, long-short quintiles or one-leg premium averages,
    none of what the harness reports for the picks alone."""
    assert edge.published is None


def test_a_blocked_event_straddle_says_what_its_placeholder_horizon_is() -> None:
    for edge_id in ("c16_pre_earnings_straddle_buy", "c17_earnings_iv_crush_sell"):
        edge = EDGES[edge_id]
        assert edge.status in CLOSED and not edge.screeners
        assert "placeholder" in edge.rejection_reason


def test_the_ranking_edges_compare_with_every_liquid_optionable_name() -> None:
    """A rank or gate over the optionable universe is read against selling on all of it: the
    plain schedules' base is the universe, and the gated edge keeps every qualified name."""
    for edge_id in ("c12_vrp_cross_section_iv_hv", "c14_delta_hedged_characteristics"):
        assert EDGES[edge_id].base == "universe" and EDGES[edge_id].top_k == 20
    c18 = EDGES["c18_iv_rank_conditional_selling"]
    assert c18.base == "universe" and c18.top_k is None and c18.schedule == "every_session"


def test_the_etf_flow_screener_orders_so_the_heaviest_creation_is_shorted_first() -> None:
    """The short leg is the lowest scores (cross_section/measuring.py ``_side_picks``): an
    ascending order on the change scores a creation low."""
    edge = EDGES["etf_flow_pressure"]
    assert edge.outcome.side == "short" and edge.top_k == 10
    path = REPO_ROOT / "config/site/presets/screeners/etf_flow_pressure/v1.toml"
    rank = tomllib.loads(path.read_text())["rank"]
    assert rank == {
        "tie_break": "rollup.etf_flows@v1.etf_shares_chg_21d",
        "tie_break_order": "asc",
    }
    variants = {v.id: v.outcome.side for v in edge.variants}
    assert variants == {"long_redemptions": "long", "long_short": "long_short"}
