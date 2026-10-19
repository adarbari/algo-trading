"""``GuideEdgeIndex``: the mechanisms in ``MECHANISM_KINDS`` order with their counts, the filters
and the edges set aside with their reasons; the Guide index's rail and section count."""

from algotrade.config.edges.document import MECHANISM_KINDS, STATUSES
from algotrade.services.read.context import StoreContext
from algotrade.services.read.guide.edges.index import (
    edge_entries,
    load_guide_edge_index,
    mechanism_entries,
)
from algotrade.services.read.guide.edges.site_edges import site_edges


def test_the_mechanisms_come_in_the_fixed_order_with_their_edges(site: StoreContext) -> None:
    index = load_guide_edge_index(site)
    assert tuple(m.id for m in index.mechanisms) == MECHANISM_KINDS
    for card in index.mechanisms:
        assert card.count == len(card.edges) == sum(s.count for s in card.statuses)
        assert [s.status for s in card.statuses] == [
            s for s in STATUSES if s in {c.status for c in card.statuses}
        ]
    assert sum(m.count for m in index.mechanisms) == len(site_edges(site))


def test_the_filters_count_every_edge_once(site: StoreContext) -> None:
    filters = load_guide_edge_index(site).filters
    total = len(site_edges(site))
    for options in (filters.assets, filters.sides, filters.holdings):
        assert sum(o.count for o in options) == total
        assert all(o.text for o in options)


def test_the_set_aside_are_the_rejected_and_blocked_with_a_reason(site: StoreContext) -> None:
    index = load_guide_edge_index(site)
    closed = [e.edge.id for e in site_edges(site) if e.edge.status in ("rejected", "blocked")]
    assert sorted(s.edge.id for s in index.set_aside) == sorted(closed)
    assert all(s.why.text for s in index.set_aside)
    assert [s.edge.status for s in index.set_aside] == sorted(
        (s.edge.status for s in index.set_aside), key=("rejected", "blocked").index
    )
    assert index.set_aside_title and index.set_aside_purpose


def test_the_ideas_not_built_are_counted_per_mechanism_and_listed(site: StoreContext) -> None:
    index = load_guide_edge_index(site)
    assert sum(m.ideas for m in index.mechanisms) == len(index.not_built) > 0
    assert index.not_built_title and index.not_built_purpose


def test_the_rail_and_the_section_count(site: StoreContext) -> None:
    rail = mechanism_entries(site)
    assert tuple(m.id for m in rail) == MECHANISM_KINDS and all(m.title for m in rail)
    assert edge_entries(site) == len(MECHANISM_KINDS) + len(site_edges(site))


def test_the_guide_serves_the_plain_reason_never_the_technical_one(site: StoreContext) -> None:
    from algotrade.services.read.guide.edges.edge import load_guide_edge  # noqa: PLC0415

    index = load_guide_edge_index(site)
    for s in index.set_aside:
        edge = next(e.edge for e in site_edges(site) if e.edge.id == s.edge.id)
        assert s.why.text == edge.plain_reason != edge.rejection_reason
        page = load_guide_edge(site, edge.id)
        assert page is not None and page.rejection is not None
        assert page.rejection.text == edge.plain_reason
        shown = " ".join([s.why.text, page.rejection.text])
        assert edge.rejection_reason[:60] not in shown
