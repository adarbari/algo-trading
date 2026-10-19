"""``GuideMechanism``: the prose of one mechanism file with the site edges that rest on it."""

from algotrade.config.edges.document import MECHANISM_KINDS
from algotrade.config.site.guide.glossary import load_guide_glossary
from algotrade.services.read.context import StoreContext
from algotrade.services.read.guide.edges.mechanism import load_guide_mechanism
from algotrade.services.read.guide.edges.site_edges import site_edges


def test_every_mechanism_page_lists_its_edges(site: StoreContext) -> None:
    listed: list[str] = []
    for kind in MECHANISM_KINDS:
        page = load_guide_mechanism(site, kind)
        assert page is not None, kind
        assert page.how_it_works and page.dont.text and page.sources
        assert {e.mechanism for e in page.edges} == ({kind} if page.edges else set())
        listed += [e.id for e in page.edges]
    assert sorted(listed) == sorted(e.edge.id for e in site_edges(site))  # each edge on one page


def test_the_edges_are_rows_with_the_tags_the_filters_need(site: StoreContext) -> None:
    page = load_guide_mechanism(site, "value_gaps")
    assert page is not None and page.edges
    row = page.edges[0]
    assert row.asset in {"stocks", "etfs", "options"} and row.side_term.startswith("side_")
    assert row.holding_sessions and row.status


def test_a_stat_source_points_into_the_sources(site: StoreContext) -> None:
    for kind in MECHANISM_KINDS:
        page = load_guide_mechanism(site, kind)
        assert page is not None
        for stat in page.stats:
            assert stat.source is None or 1 <= stat.source <= len(page.sources)


def test_see_also_names_glossary_terms_only(site: StoreContext) -> None:
    terms = {t.id for t in load_guide_glossary(site.configs).terms}
    for kind in MECHANISM_KINDS:
        page = load_guide_mechanism(site, kind)
        assert page is not None and set(page.see_also) <= terms and page.see_also


def test_no_such_mechanism_is_none(site: StoreContext) -> None:
    assert load_guide_mechanism(site, "nope") is None


def test_a_second_read_of_a_mechanism_reads_no_config(counted) -> None:  # type: ignore[no-untyped-def]
    ctx, configs = counted
    first = load_guide_mechanism(ctx, "value_gaps")
    seen = configs.loads
    assert load_guide_mechanism(ctx, "value_gaps") is first
    assert configs.loads == seen
