"""``load_guide_screener_category``: one family's page: its purpose and intro, its screeners as
rows in Guide order with the line they ask in and the site edges that use them; ``None`` for an
id that is no family or a family with no site screener."""

from algotrade.config.site.guide.screeners import load_guide_screeners
from algotrade.config.site.guide.sections import load_guide_sections
from algotrade.services.read.context import StoreContext
from algotrade.services.read.guide.edges.site_edges import edges_of_screener
from algotrade.services.read.guide.screeners.category import load_guide_screener_category
from tests.unit.services.read.guide.conftest import SHIPPED


def test_the_family_page(ctx: StoreContext) -> None:
    page = load_guide_screener_category(ctx, "trend")
    assert page is not None
    assert (page.id, page.title) == ("trend", "Trend")
    assert (page.purpose, page.intro) == ("Shares already rising.", "Charts first.")
    (alpha,) = page.screeners  # the listed id that is no preset is left out
    assert (alpha.id, alpha.name, alpha.line) == ("alpha", "Alpha", "Dips in a rising share.")
    assert alpha.edges == ()


def test_an_unknown_family_and_a_family_without_screeners_have_no_page(ctx: StoreContext) -> None:
    assert load_guide_screener_category(ctx, "nope") is None
    assert load_guide_screener_category(ctx, "empty") is None


def test_every_shipped_family_has_a_page_whose_rows_carry_the_edges_that_use_them(
    site: StoreContext,
) -> None:
    prose = load_guide_screeners(SHIPPED)
    for family in load_guide_sections(SHIPPED).families:
        page = load_guide_screener_category(site, family.id)
        assert page is not None, family.id
        assert [s.id for s in page.screeners] == list(family.presets)
        for row in page.screeners:
            assert row.line == prose.get(row.id).line  # type: ignore[union-attr]
            assert [e.id for e in row.edges] == [e.edge.id for e in edges_of_screener(site, row.id)]
