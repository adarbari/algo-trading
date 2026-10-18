"""The edge build's fundamentals edges (E2): each is a candidate frozen from 2026-04-01 with its
screener presets, and every screener ranks the side the edge's thesis puts first (a ranking
that points the wrong way would score the avoid list as the buy list), the BDC hand list is the
same in the screener and the universe, and only the edge with a verified figure carries one."""

import tomllib
from datetime import date

import pytest

from algotrade.config.edges.loading import load_edges
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT

PRESETS = REPO_ROOT / "config" / "site" / "presets"
EDGES = {e.id: e for e in load_edges(FileConfigStore(REPO_ROOT / "config", local=False))}
# edge -> (screener, which end of its ranking the edge's main outcome takes: the screener's
# rank order and the thesis' favoured name first)
RANKS = {
    "cash_based_operating_profitability": {
        "cash_op_profitability": "desc",
    },
    "composite_value": {"composite_value": "desc"},
    "quality_minus_junk": {"qmj": "desc"},
    "net_share_issuance": {"net_share_issuance": "asc"},  # most negative issuance (buybacks) first
    "asset_growth": {
        "asset_growth": "asc"
    },  # slowest growers first; the main outcome shorts the last
    "distress_failure_probability": {
        "distress_ohlson": "asc"
    },  # safest first; the last are shorted
    "bdc_price_to_nav_reversion": {"bdc_price_to_nav": "asc"},  # the deepest discount first
}


def preset(screener: str) -> dict:
    return tomllib.loads((PRESETS / "screeners" / screener / "v1.toml").read_text())


@pytest.mark.parametrize("edge_id", RANKS)
def test_each_edge_is_a_candidate_from_the_frozen_date_with_its_screeners(edge_id: str) -> None:
    edge = EDGES[edge_id]
    assert edge.status == "candidate" and edge.frozen_from == date(2026, 4, 1)
    assert edge.family in ("A", "H") and set(edge.screeners) == set(RANKS[edge_id])
    assert edge.outcome.kind == "excess_return" and edge.outcome.start_offset_sessions == 1


@pytest.mark.parametrize(
    ("edge_id", "screener", "order"),
    [(e, s, o) for e, ranks in RANKS.items() for s, o in ranks.items()],
)
def test_a_screener_ranks_the_favoured_name_first(edge_id: str, screener: str, order: str) -> None:
    rank = preset(screener)["rank"]
    assert rank["tie_break_order"] == order
    assert rank["tie_break"] in {c["field"] for c in preset(screener)["criteria"].values()}


@pytest.mark.parametrize("edge_id", ["asset_growth", "distress_failure_probability"])
def test_an_avoid_list_edge_holds_its_bottom_names_short_and_the_long_side_is_a_variant(
    edge_id: str,
) -> None:
    edge = EDGES[edge_id]
    assert edge.outcome.side == "short"
    assert {v.outcome.side for v in edge.variants} == {"long", "long_short"}


def test_net_share_issuance_is_long_the_buybacks_with_the_issuers_as_a_short_variant() -> None:
    edge = EDGES["net_share_issuance"]
    assert edge.outcome.side == "long"
    assert {v.id: v.outcome.side for v in edge.variants} == {
        "issuers_short": "short",
        "spread": "long_short",
    }


def test_the_bdc_hand_list_is_the_same_in_the_screener_and_the_universe() -> None:
    criteria = preset("bdc_price_to_nav")["criteria"]
    screener = criteria["bdc"]["value"]
    assert criteria["nav_fresh"]["value"] == 135  # the book is at most a quarter and a filing old
    where = tomllib.loads((PRESETS / "selections" / "bdc_listed.toml").read_text())["where"]["all"]
    universe = next(c["value"] for c in where if c["field"] == "instrument.instrument_id")
    assert screener == universe and len(set(screener)) == len(screener) >= 30
    assert EDGES["bdc_price_to_nav_reversion"].universe == "bdc_listed"


def test_only_the_edge_with_a_verified_figure_carries_a_published_one() -> None:
    published = {i: EDGES[i].published for i in RANKS if EDGES[i].published}
    assert list(published) == ["cash_based_operating_profitability"]  # composite_value has none
    figure = published["cash_based_operating_profitability"]
    assert figure.measure == "decile_spread" and figure.value == pytest.approx(0.0047)
    assert (
        figure.horizon_sessions
        in EDGES["cash_based_operating_profitability"].outcome.horizon_sessions
    )
