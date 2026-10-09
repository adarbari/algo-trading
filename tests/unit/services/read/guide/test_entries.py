"""``load_guide_entries``: the entries many refs name in one read, each distinct ref once, in the
order of the refs, a ref with no entry left out."""

from algotrade.services.read.context import StoreContext
from algotrade.services.read.guide.entries import GuideEntryKind, GuideRef, load_guide_entries


def test_the_entries_the_refs_name(regime: StoreContext) -> None:
    refs = [
        GuideRef(GuideEntryKind.EPISODE, "gfc"),
        GuideRef(GuideEntryKind.INDICATOR, "curve"),
        GuideRef(GuideEntryKind.INDICATOR, "curve"),
        GuideRef(GuideEntryKind.INDICATOR, "nope"),
        GuideRef(GuideEntryKind.TERM, "nope"),
        GuideRef(GuideEntryKind.START, "nope"),
    ]
    found = load_guide_entries(regime, refs)
    assert [i.key for i in found.indicators] == ["curve"]
    assert [e.slug for e in found.episodes] == ["gfc"]
    assert found.terms == () and found.start_pages == ()
