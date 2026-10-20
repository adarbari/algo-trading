"""``GuideScreenerIndex``: the Screeners lead page: what a screener is and how it differs from an
edge (``sections.toml``'s ``screeners_page``), a card per family in Guide order with its count (a
family with no site screener has no card), and the count of every screener."""

from algotrade.services.read.context import StoreContext
from algotrade.services.read.guide.screeners.index import (
    GuideScreenerCategoryCard,
    load_guide_screener_index,
)
from algotrade.services.read.guide.screeners.site_screeners import site_screeners
from tests.unit.services.read.guide.conftest import DOCUMENTS, stores


def test_the_lead_page_has_a_card_per_family_with_screeners(ctx: StoreContext) -> None:
    index = load_guide_screener_index(ctx)
    assert index.what == "A screener is a saved rule screen."
    assert index.versus_edge.startswith("An edge is a claim")
    # "empty" lists only a preset that does not exist: no card; trend holds alpha.
    assert index.categories == (
        GuideScreenerCategoryCard("trend", "Trend", "Shares already rising.", 1),
    )
    assert index.count == len(site_screeners(ctx)) == 2  # alpha and zeta (in no family)


def test_without_the_lead_table_the_texts_are_empty() -> None:
    sections = dict(DOCUMENTS[("site", "guide", "sections")])
    del sections["screeners_page"]
    index = load_guide_screener_index(
        stores({**DOCUMENTS, ("site", "guide", "sections"): sections})
    )
    assert (index.what, index.versus_edge) == ("", "")


def test_the_shipped_cards_count_every_site_screener_once(site: StoreContext) -> None:
    index = load_guide_screener_index(site)
    assert index.what and index.versus_edge
    assert [c.id for c in index.categories][:2] == ["trend", "breakouts"]
    assert all(c.title and c.purpose and c.count for c in index.categories)
    assert sum(c.count for c in index.categories) == index.count == len(site_screeners(site))
