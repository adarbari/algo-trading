"""``structured_matches`` and ``resolves_fully`` over the shipped phrasebook and the golden
sentences: a sentence resolves only when structured entries with exact thresholds claim every
content word of it."""

import pytest

from algotrade.config.site.settings import load_phrasebook
from algotrade.services.drafting.golden import load_cases
from algotrade.services.drafting.phrasebook.resolve import (
    resolve,
    resolves_fully,
    structured_matches,
)
from algotrade.storage.factory import open_config_store
from tests.conftest import REPO_ROOT

BOOK = load_phrasebook(open_config_store(REPO_ROOT / "config")).phrases
GOLDEN = {
    c.id: c.sentence for c in load_cases(REPO_ROOT / "tests" / "fixtures" / "drafting" / "golden")
}


def fields(sentence: str) -> list[tuple[str, str, object]]:
    got = resolves_fully(sentence, BOOK)
    assert got is not None, sentence
    return [(c["field"], c["op"], c.get("value")) for c in got]


def test_a_golden_sentence_of_structured_words_resolves() -> None:
    assert fields(GOLDEN["volatile-small-caps"]) == [
        ("feature.market_cap", "lt", 2_000_000_000),
        ("feature.atr_pct", "gte", 0.03),
    ]  # file order


@pytest.mark.parametrize(
    "case",
    [
        "uptrend-no-earnings",  # "10 sessions" and "more than" are not covered
        "optionable-iv-rank-liquid",  # numbers; "liquid" has three readings
        "bullish-engulfing-at-support",  # no structured entry says it
        "cheap-on-sales-high-margin",  # "net margin > 20%" is not a word of an entry
        "outperforming-spy-3m",  # "3 months"
    ],
)
def test_golden_sentences_with_a_gap_do_not_resolve(case: str) -> None:
    assert resolves_fully(GOLDEN[case], BOOK) is None


def test_thresholds_and_flags_resolve_in_file_order_without_duplicates() -> None:
    got = fields("optionable ETFs that are oversold and in an uptrend")
    assert got == [
        ("rollup.momentum@v1.rsi_14", "lt", 30),
        ("feature.trend_state", "eq", "UPTREND"),
        ("instrument.security_type", "in", ["ETF"]),
        ("instrument.status", "eq", "ACTIVE"),
        ("instrument.optionable", "eq", True),
    ]


def test_the_longest_wording_wins() -> None:
    (a,) = [(c["field"], c["op"]) for c in resolves_fully("breaking out to highs", BOOK) or ()]
    assert a == ("feature.pct_from_high_52w", "gte")  # not also "breaking out"


@pytest.mark.parametrize(
    "sentence",
    ["", "oversold with a good story", "oversold over 5 dollars", "liquid", "weird"],
)
def test_no_structured_cover_is_none(sentence: str) -> None:
    assert resolves_fully(sentence, BOOK) is None


def test_two_readings_of_one_field_are_not_resolved() -> None:
    assert resolves_fully("near the 52-week low and off the lows", BOOK) is None


def test_structured_matches_are_the_structured_entries_the_sentence_says() -> None:
    said = structured_matches("liquid stocks that are oversold, plus momentum", BOOK)
    assert [p.say[0] for p in said] == ["oversold", "liquid", "stocks"]
    assert structured_matches("momentum", BOOK) == ()  # a free-text entry


@pytest.mark.parametrize(
    "sentence",
    [
        "uptrend stocks without earnings this week",  # "without" flips "earnings this week"
        "less volatile stocks",  # a comparative: not "atr_pct gte 0.03"
        "small cap or large cap",  # "or": both would apply and select nothing
        "stocks not in an uptrend",  # negation
        "non optionable ETFs",
        "uptrend stocks except oversold ones",
        "more volatile stocks",
        "small caps excluding ETFs",
        "oversold or in an uptrend",
        "stocks never in a downtrend",
    ],
)
def test_negation_comparatives_and_or_are_never_filler(sentence: str) -> None:
    assert resolves_fully(sentence, BOOK) is None


@pytest.mark.parametrize(
    "sentence",
    [
        "oversold and overbought stocks",  # rsi lt 30 and gt 70: no value
        "large caps that are small caps",
        "uptrend and downtrend stocks",
        "ETFs and stocks",  # two disjoint security types
        "earnings soon and avoid earnings",
    ],
)
def test_criteria_that_cannot_both_hold_are_not_resolved(sentence: str) -> None:
    assert structured_matches(sentence, BOOK)
    assert resolves_fully(sentence, BOOK) is None


def test_a_flipping_word_a_wording_covers_does_not_block() -> None:
    got = fields("stocks with no earnings coming")  # "no" is part of the entry's own wording
    assert ("rollup.earnings@v1.days_to_earnings", "gt", 10) in got


@pytest.mark.parametrize(
    "sentence",
    ["oversold then breakout", "oversold followed by a breakout", "oversold after a breakout"],
)
def test_a_sequence_is_not_two_simultaneous_gates(sentence: str) -> None:
    assert resolves_fully(sentence, BOOK) is None


def test_resolve_says_where_each_wording_is_in_the_sentence() -> None:
    sentence = "Liquid stocks that are OVERSOLD"
    got = resolve("oversold stocks in an uptrend", BOOK)
    assert got is not None and got.criteria == resolves_fully("oversold stocks in an uptrend", BOOK)
    said = "oversold stocks in an uptrend"
    assert [said[c.start : c.end] for c in got.claims] == ["oversold", "stocks", "in an uptrend"]
    assert [c.phrase.say[0] for c in got.claims] == ["oversold", "stocks", "uptrend"]
    assert resolve(sentence, BOOK) is None  # "liquid" has several readings: ask
    capital = resolve("Oversold ETFs", BOOK)
    assert capital is not None and "Oversold ETFs"[capital.claims[1].start :] == "ETFs"


def test_resolve_declines_a_sentence_whose_lower_case_is_longer() -> None:
    assert resolve("İstanbul oversold", BOOK) is None  # offsets would not be its own words
