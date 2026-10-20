"""``load_guide_screener``: a site screener's page from the latest preset version and its
prose file: the prose linked at catalogue names, the family and its title, the criteria rows
in file order (asks, field, rule, mode, on_miss for soft only), the tie-break, related
screeners (an id that is no screener dropped) and the situations that fool the fields it
decides on; ``None`` for no such preset; a preset without a prose file still has its table."""

from algotrade.services.read.context import StoreContext
from algotrade.services.read.guide.prose import ProseSegment
from algotrade.services.read.guide.screeners.screener import (
    GuideCriterionRow,
    GuideRelatedScreener,
    GuideScreenerSituation,
    GuideScreenerSource,
    load_guide_screener,
)
from tests.unit.services.read.guide.conftest import ADV, CLOSE, PULLBACK, REL_VOLUME


def test_the_screener_page(ctx: StoreContext) -> None:
    page = load_guide_screener(ctx, "alpha")
    assert page is not None
    assert (page.id, page.name, page.version) == ("alpha", "Alpha", 2)  # the latest version
    assert (page.family, page.family_title) == ("trend", "Trend")
    assert page.prose is not None
    assert page.prose.summary.segments == (
        ProseSegment("Finds dips; read "),
        ProseSegment(PULLBACK, PULLBACK),
        ProseSegment(" first."),
        ProseSegment("[^1]", source=1),  # a marker is its own segment
    )
    assert page.prose.before_acting[0].fields == (ADV,)
    assert page.prose.before_acting[0].sources == (2,)
    assert page.prose.sources == (
        GuideScreenerSource("A book", "https://example.com/book", "The dip."),
        GuideScreenerSource("A paper", None, "No page found."),
    )
    assert (page.tie_break, page.tie_break_descending) == (PULLBACK, True)


def test_the_criteria_rows_in_file_order(ctx: StoreContext) -> None:
    page = load_guide_screener(ctx, "alpha")
    assert page is not None
    assert page.criteria == (
        GuideCriterionRow("adv", "Trades $50M a day", ADV,
                          "gte 50000000 soft tolerance relative 0.2 on_miss LIQUIDITY_RISK",
                          "soft", "LIQUIDITY_RISK"),
        GuideCriterionRow("band", "Near its average", PULLBACK,
                          "between [-0.5, 0.5] soft tolerance 0.25", "soft", "WATCH"),
        GuideCriterionRow("listed", None, "instrument.status", "eq ACTIVE hard", "hard", None),
    )  # fmt: skip


def test_related_screeners_and_situations(ctx: StoreContext) -> None:
    page = load_guide_screener(ctx, "alpha")
    assert page is not None
    assert page.related == (GuideRelatedScreener("zeta", "Zeta", "the other one"),)
    # thin name fools adv (a criterion); takeover fools rel_volume, which alpha does not read.
    assert page.situations == (GuideScreenerSituation("thin-name", "thin name", (ADV,)),)


def test_a_screener_without_prose_and_a_flag_field(ctx: StoreContext) -> None:
    page = load_guide_screener(ctx, "zeta")
    assert page is not None and page.prose is None and page.related == ()
    assert (page.family, page.family_title) == (None, None)
    assert [c.asks for c in page.criteria] == [None]
    # zeta reads adv only as a display column: not a field it decides on.
    assert page.situations == (
        GuideScreenerSituation("thin-name", "thin name", (CLOSE,)),
        GuideScreenerSituation("takeover", "takeover", (REL_VOLUME,)),  # a flag's field
    )


def test_no_such_screener(ctx: StoreContext) -> None:
    assert load_guide_screener(ctx, "missing") is None
    assert load_guide_screener(ctx, "broken") is None  # not a rule screen
