"""An item goes to the part the model tagged it with, else the part that contains its span, else
the part whose words say a phrasebook entry for its field, else a catch-all (``kept`` when the
Builder's document already had it, ``unplaced`` otherwise), in that order."""

from algotrade.config.site.llm import Phrase
from algotrade.services.drafting.parts.attribute import Placed, attribute
from algotrade.services.drafting.parts.model import KEPT_ID, UNPLACED_ID, Item

PLACED = [Placed("p1", "liquid stocks"), Placed("p2", "IV rank above 50%")]
BOOK = [
    Phrase(("liquid",), ("rollup.price_stats@v2.adv_usd_20d",)),
    Phrase(("iv rank",), ("feature.iv_rank",)),
]


def test_the_models_tag_wins_over_every_fallback() -> None:
    item = Item("criteria", "a", tag="p2", field="rollup.price_stats@v2.adv_usd_20d")
    got, tagged = attribute([item], PLACED, BOOK)
    assert got == {"p2": [item]} and tagged == 1  # the phrasebook would have said p1


def test_a_tag_naming_no_located_part_falls_through_to_the_span() -> None:
    item = Item("missing", "m", tag="p9", span="iv rank")
    got, tagged = attribute([item], PLACED, BOOK)
    assert got == {"p2": [item]} and tagged == 0


def test_the_span_comes_before_the_phrasebook() -> None:
    item = Item("unresolved", "liquid", span="IV rank", field="rollup.price_stats@v2.adv_usd_20d")
    assert attribute([item], PLACED, BOOK)[0] == {"p2": [item]}


def test_a_span_with_a_typo_is_still_contained() -> None:
    item = Item("unresolved", "liquid", span="liqiud stocks")
    assert attribute([item], PLACED, BOOK)[0] == {"p1": [item]}


def test_the_phrasebook_places_an_untagged_criterion_by_its_field() -> None:
    item = Item("criteria", "iv", field="feature.iv_rank")
    assert attribute([item], PLACED, BOOK)[0] == {"p2": [item]}


def test_nothing_fits_a_criterion_carried_over_is_kept_and_another_is_unplaced() -> None:
    carried = Item("criteria", "old", field="feature.other", carried=True)
    stray = Item("criteria", "new", field="feature.other")
    suggestion = Item("suggestions", "s1", field="feature.other")
    got, tagged = attribute([carried, stray, suggestion], PLACED, BOOK)
    assert got == {KEPT_ID: [carried], UNPLACED_ID: [stray, suggestion]} and tagged == 0


def test_an_item_with_no_part_to_go_to_is_still_placed() -> None:
    item = Item("criteria", "a", tag="p1")
    assert attribute([item], [], BOOK)[0] == {UNPLACED_ID: [item]}
