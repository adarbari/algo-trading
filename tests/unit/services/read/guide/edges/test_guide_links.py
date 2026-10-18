"""How the Edges section joins the rest of the Guide: the Guide index (the section's count and
the rail), the playbook page's backlinks, the batched entries and the one search."""

import time

from algotrade.config.edges.document import MECHANISM_KINDS
from algotrade.services.read.context import StoreContext
from algotrade.services.read.guide.edges.site_edges import site_edges
from algotrade.services.read.guide.entries import GuideEntryKind, GuideRef, load_guide_entries
from algotrade.services.read.guide.index import load_guide_index
from algotrade.services.read.guide.playbook import load_guide_playbook
from algotrade.services.read.guide.search import entry_titles, load_guide_search


def test_the_guide_index_counts_the_edges_section_and_lists_the_rail(site: StoreContext) -> None:
    index = load_guide_index(site)
    section = next(s for s in index.sections if s.id == "edges")
    assert section.entries == len(MECHANISM_KINDS) + len(site_edges(site))
    assert tuple(m.id for m in index.mechanisms) == MECHANISM_KINDS
    assert sum(m.count for m in index.mechanisms) == len(site_edges(site))


def test_a_playbook_page_lists_the_edges_it_implements(site: StoreContext) -> None:
    page = load_guide_playbook(site, "momentum_12_1")
    assert page is not None
    assert "momentum_12_1" in [e.id for e in page.edges]
    assert all(e.id in {x.edge.id for x in site_edges(site)} for e in page.edges)
    for edge in site_edges(site):  # the other way round: every edge shows on its playbooks
        for playbook in edge.playbooks:
            shown = load_guide_playbook(site, playbook)
            assert shown is not None and edge.edge.id in [e.id for e in shown.edges]


def test_the_batched_read_serves_mechanisms_and_edges(site: StoreContext) -> None:
    refs = [
        GuideRef(GuideEntryKind.EDGE, "momentum_12_1"),
        GuideRef(GuideEntryKind.MECHANISM, "slow_to_update"),
        GuideRef(GuideEntryKind.EDGE, "momentum_12_1"),
        GuideRef(GuideEntryKind.EDGE, "nope"),
        GuideRef(GuideEntryKind.MECHANISM, "nope"),
    ]
    found = load_guide_entries(site, refs)
    assert [e.summary.id for e in found.edges] == ["momentum_12_1"]
    assert [m.id for m in found.mechanisms] == ["slow_to_update"]


def test_the_search_finds_a_mechanism_and_an_edge(site: StoreContext) -> None:
    by_title = load_guide_search(site, "Forced buyers and sellers", 5)
    assert (by_title.groups[0].kind, by_title.groups[0].hits[0].id) == ("mechanism", "forced_flows")
    edge = next(e for e in site_edges(site) if e.edge.id == "momentum_12_1")
    found = load_guide_search(site, edge.edge.name, 5)
    hit = next(h for g in found.groups if g.kind == "edge" for h in g.hits)
    assert hit.id == "momentum_12_1" and hit.title == edge.edge.name
    assert entry_titles(site)[("edge", "momentum_12_1")] == edge.edge.name
    assert entry_titles(site)[("mechanism", "forced_flows")] == "Forced buyers and sellers"


def test_a_users_draft_never_shows_in_search_or_the_batched_read(with_draft: StoreContext) -> None:
    found = load_guide_search(with_draft, "draft", 50)
    assert "guide_draft_edge" not in [h.id for g in found.groups for h in g.hits]
    refs = [GuideRef(GuideEntryKind.EDGE, "guide_draft_edge")]
    assert load_guide_entries(with_draft, refs).edges == ()


def test_the_search_keeps_its_budget_with_every_edge_in_it(site: StoreContext) -> None:
    load_guide_search(site, "earnings", 5)  # warm: the edges are read once per cache
    start = time.perf_counter()
    load_guide_search(site, "earnings", 5)
    assert time.perf_counter() - start < 0.5
