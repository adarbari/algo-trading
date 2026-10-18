"""The event edges and avoid lists of EB E3: each short-side edge's screener orders so the
harness's short leg (the lowest scores) takes the most liquid names first, a long event edge's
screener ranks best first, every non-blocked event edge declares a field the harness reads, and a
blocked one says what is missing."""

import tomllib

import pytest

from algotrade.config.edges.document import CLOSED, Edge
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
