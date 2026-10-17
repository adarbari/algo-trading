"""The deterministic verifier (ADR 0041, amended 2026-10-17): each doubt kind on real sentences
(positive and negative), one doubt per part, and no doubt for what is understood."""

from algotrade.services.drafting.parts.build import build_parts
from algotrade.services.drafting.parts.model import Item, Part
from algotrade.services.drafting.parts.verify import KINDS, Doubt, doubts, kinds_of


def parts_of(sentence: str, raw: list[dict[str, str]], *items: Item) -> tuple[Part, ...]:
    built = build_parts(sentence, raw, list(items), [])
    assert built is not None
    return built[0]


def crit(ref: str, tag: str | None = None) -> Item:
    return Item("criteria", ref, tag=tag)


def kinds(found: tuple[Doubt, ...]) -> list[tuple[str, str]]:
    return [(d.kind, d.ref) for d in found]


def test_cheap_on_pe_split_is_two_unmapped_words_doubts() -> None:
    """The 2026-10-17 'cheap' / 'on P/E' split: the words around the part map to nothing."""
    parts = parts_of(
        "cheap stocks on P/E as long as revenue is still growing",
        [{"id": "p1", "words": "stocks"}, {"id": "p2", "words": "revenue is still growing"}],
        crit("pe", "p1"), crit("rev", "p2"),
    )  # fmt: skip
    found = doubts(parts)
    assert kinds(found) == [("unmapped_words", "g1"), ("unmapped_words", "g2")]
    assert "cheap" in found[0].message and "map them" in found[0].message


def test_glue_and_connectors_alone_are_no_doubt() -> None:
    parts = parts_of(
        "show me stocks over $50 and with growth",
        [{"id": "p1", "words": "stocks over $50"}, {"id": "p2", "words": "growth"}],
        crit("price", "p1"), crit("g", "p2"),
    )  # fmt: skip
    assert doubts(parts) == ()


def test_an_or_left_out_of_the_words_is_a_connector_doubt() -> None:
    parts = parts_of(
        "stocks with RSI under 30 or within 5% of their 52-week low",
        [{"id": "p1", "words": "stocks with RSI under 30"}],
        crit("rsi", "p1"),
    )  # fmt: skip
    found = doubts(parts)
    assert kinds(found) == [("connector_left_out", "g1")]
    assert "one boolean formula" in found[0].message


def test_a_negation_left_out_says_to_keep_it_in_the_words() -> None:
    parts = parts_of(
        "RSI under 30 unless volume is thin",
        [{"id": "p1", "words": "RSI under 30"}],
        crit("rsi", "p1"),
    )  # fmt: skip
    found = doubts(parts)
    assert kinds(found) == [("connector_left_out", "g1")]
    assert "negation" in found[0].message


def test_a_criterion_with_no_words_is_unplaced() -> None:
    parts = parts_of(
        "RSI under 30",
        [{"id": "p1", "words": "RSI under 30"}],
        crit("rsi", "p1"), crit("volume"),
    )  # fmt: skip
    found = doubts(parts)
    assert kinds(found) == [("unplaced", "unplaced")]
    assert "volume" in found[0].message and "drop it" in found[0].message


def test_or_drafted_as_two_anded_criteria_is_a_doubt() -> None:
    parts = parts_of(
        "stocks with RSI under 30 or within 5% of their 52-week low",
        [{"id": "p1", "words": "stocks with RSI under 30 or within 5% of their 52-week low"}],
        crit("rsi", "p1"), crit("low", "p1"),
    )  # fmt: skip
    assert kinds(doubts(parts)) == [("or_not_formula", "p1")]


def test_or_with_a_formula_or_one_criterion_or_inside_a_token_is_no_doubt() -> None:
    sentence = "stocks with RSI under 30 or within 5% of their 52-week low"
    words = [{"id": "p1", "words": sentence}]
    with_formula = parts_of(sentence, words, Item("formulas", "either", tag="p1"), crit("a", "p1"))
    one = parts_of(sentence, words, crit("rsi", "p1"))
    long = "float over 5 and short_float_or_more"
    token = parts_of(long, [{"id": "p1", "words": long}], crit("a", "p1"), crit("b", "p1"))
    assert doubts(with_formula) == () and doubts(one) == () and doubts(token) == ()


def test_kept_parts_and_no_parts_are_no_doubt() -> None:
    parts = parts_of(
        "RSI under 30", [{"id": "p1", "words": "RSI under 30"}],
        crit("rsi", "p1"), Item("criteria", "old", carried=True),
    )  # fmt: skip
    assert doubts(parts) == () and doubts(None) == ()


def test_kinds_are_a_small_closed_set() -> None:
    assert set(KINDS) == {"unmapped_words", "connector_left_out", "unplaced", "or_not_formula"}
    assert kinds_of(()) == ()
