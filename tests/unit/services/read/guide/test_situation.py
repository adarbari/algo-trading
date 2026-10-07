"""``load_guide_situation``: a situation by its slug: signs and do linked at catalogue names,
the fields it fools as written, and the site playbooks deciding on any of them with those
fields; ``None`` for an unknown slug."""

from algotrade.services.read.context import StoreContext
from algotrade.services.read.guide.situation import GuideSituationPlaybook, load_guide_situation
from tests.unit.services.read.guide.conftest import ADV, CLOSE, REL_VOLUME


def test_the_situation_page(ctx: StoreContext) -> None:
    page = load_guide_situation(ctx, "thin-name")
    assert page is not None
    assert (page.slug, page.name, page.affects) == ("thin-name", "thin name", (ADV, CLOSE))
    assert page.signs.text == "Few trades." and page.signs.fields == ()
    assert page.do.text == "Gate."
    assert page.playbooks == (
        GuideSituationPlaybook("alpha", "Alpha", (ADV,)),
        GuideSituationPlaybook("zeta", "Zeta", (CLOSE,)),
    )


def test_a_flag_field_counts_and_unknown_slugs_are_none(ctx: StoreContext) -> None:
    page = load_guide_situation(ctx, "takeover")
    assert page is not None
    assert page.playbooks == (GuideSituationPlaybook("zeta", "Zeta", (REL_VOLUME,)),)
    assert load_guide_situation(ctx, "thin name") is None  # the name is not the slug
    assert load_guide_situation(ctx, "nope") is None
