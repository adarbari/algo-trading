"""``site_edges``: every site edge once, in Guide order, never a user's; the tags the Guide
derives (asset class, side, holding band) and the playbook links both ways."""

from dataclasses import replace

import pytest

from algotrade.config.edges.document import MECHANISM_KINDS
from algotrade.config.edges.loading import load_edges
from algotrade.services.read.context import StoreContext
from algotrade.services.read.guide.edges.schedule import BANDS
from algotrade.services.read.guide.edges.site_edges import (
    edges_of_playbook,
    playbooks_of,
    site_edges,
)
from algotrade.services.read.guide.edges.universe import ASSETS, asset_of, universe_of
from tests.unit.services.read.guide.edges.conftest import DRAFT_ID, DRAFT_USER


def test_every_site_edge_is_listed_once_in_guide_order(site: StoreContext) -> None:
    found = site_edges(site)
    assert sorted(e.edge.id for e in found) == sorted(site.configs.names("site", "edges"))
    assert [(e.edge.name.lower(), e.edge.id) for e in found] == sorted(
        (e.edge.name.lower(), e.edge.id) for e in found
    )


def test_the_order_is_the_same_for_every_store_instance(
    site: StoreContext, with_draft: StoreContext
) -> None:
    assert [e.edge.id for e in site_edges(site)] == [e.edge.id for e in site_edges(with_draft)]


def test_a_users_draft_never_appears(with_draft: StoreContext) -> None:
    configs = with_draft.configs
    assert DRAFT_ID in [e.id for e in load_edges(configs, DRAFT_USER)]  # the control: theirs
    assert DRAFT_ID not in [e.edge.id for e in site_edges(with_draft)]
    assert all(e.edge.owner == "site" for e in site_edges(with_draft))


def test_every_site_edge_has_a_mechanism_page(site: StoreContext) -> None:
    assert [e.edge.id for e in site_edges(site) if e.mechanism not in MECHANISM_KINDS] == []


@pytest.mark.parametrize(
    ("edge_id", "asset"),
    [
        ("momentum_12_1", "stocks"),
        ("bdc_price_to_nav_reversion", "stocks"),
        ("closed_end_fund_discounts", "etfs"),
        ("commodity_roll_momentum", "etfs"),
        ("c16_pre_earnings_straddle_buy", "options"),
    ],
)
def test_the_asset_class_rule(site: StoreContext, edge_id: str, asset: str) -> None:
    found = next(e for e in site_edges(site) if e.edge.id == edge_id)
    assert found.asset == asset
    assert {e.asset for e in site_edges(site)} <= set(ASSETS)


def test_an_option_outcome_wins_over_the_universe(site: StoreContext) -> None:
    stock = next(e for e in site_edges(site) if e.edge.id == "momentum_12_1")
    options = replace(stock.edge, outcome=replace(stock.edge.outcome, kind="option_pnl"))
    assert asset_of(options, universe_of(site, options)) == "options"
    assert asset_of(stock.edge, universe_of(site, stock.edge)) == "stocks"


def test_side_holding_and_band(site: StoreContext) -> None:
    for e in site_edges(site):
        assert e.side == e.edge.outcome.result_side
        assert e.holding == e.edge.outcome.horizon_sessions
        assert e.band in BANDS
        assert e.holding_text.endswith(("session", "sessions"))
    short = next(e for e in site_edges(site) if e.edge.id == "momentum_12_1")
    assert (short.holding, short.band) == ((20,), "medium")


def test_every_playbook_link_round_trips(site: StoreContext) -> None:
    ids = {p.id for p in playbooks_of(site)}
    for e in site_edges(site):
        assert set(e.playbooks) <= ids
        assert set(e.playbooks) <= set(e.edge.screeners)
        for playbook in e.playbooks:
            assert e.edge.id in [x.edge.id for x in edges_of_playbook(site, playbook)]
    for playbook in ids:
        for e in edges_of_playbook(site, playbook):
            assert playbook in e.edge.screeners
    assert any(edges_of_playbook(site, p) for p in ids)  # some playbook implements an edge
