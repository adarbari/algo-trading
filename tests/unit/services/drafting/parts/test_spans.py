"""Where a part's words are in the sentence: exact, ignoring case, with a typo; repeated words are
found in order; no match is ``None``; a short or numeric token is never fuzzy; offsets convert to
UTF-16 code units (a non-ASCII sentence slices back to the same words in a browser); the gaps."""

from algotrade.services.drafting.parts.spans import (
    Join,
    Span,
    Stretch,
    locate,
    stretches,
    tokens,
    utf16,
)

SENTENCE = "liquid stocks with IV rank above 50% and no earnings in the next 10 sessions"


def said(sentence: str, words: str, after: int = 0) -> str | None:
    span = locate(sentence, words, after)
    return None if span is None else sentence[span.start : span.end]


def test_exact_words_are_found_on_word_boundaries() -> None:
    assert said(SENTENCE, "IV rank above 50%") == "IV rank above 50%"
    assert said("ETFs only", "ETF") is None  # a part of a word is not the word


def test_case_is_ignored_and_the_sentences_own_case_is_served() -> None:
    assert said(SENTENCE, "iv RANK") == "IV rank"


def test_a_typo_in_a_long_token_is_found_but_a_short_or_numeric_token_must_match() -> None:
    assert said("stocks with high volumne", "high volume") == "high volumne"  # a substitution
    assert said("liquid stocks", "liqiud stocks") == "liquid stocks"  # two letters swapped
    assert said("above 2026 close", "above 2025 close") is None  # a digit is never a typo
    assert said("buy the dip", "buy the dop") is None  # a short token must match exactly


def test_words_repeated_in_the_sentence_are_found_after_the_previous_part() -> None:
    sentence = "above 50 and below 20 and above 50 again"
    first = locate(sentence, "above 50")
    assert first == Span(0, 8)
    second = locate(sentence, "above 50", first.end if first else 0)
    assert second == Span(26, 34)
    assert locate(sentence, "above 50", 34) is None  # nothing after the last one


def test_words_not_in_the_sentence_or_empty_are_not_found() -> None:
    assert locate(SENTENCE, "dividend yield") is None
    assert locate(SENTENCE, "   ") is None
    assert locate(SENTENCE, "50% rank IV above") is None  # the words must be in order


def test_utf16_offsets_count_what_the_browser_counts() -> None:
    sentence = "café stocks 🚀 with IV rank above 50% naïve"
    span = locate(sentence, "IV rank above 50%")
    assert span is not None
    start, end = utf16(sentence, span.start), utf16(sentence, span.end)
    units = sentence.encode("utf-16-le")
    assert units[2 * start : 2 * end].decode("utf-16-le") == "IV rank above 50%"
    assert start == span.start + 1  # the rocket is two UTF-16 units, one code point
    assert utf16(sentence, 0) == 0


def test_non_ascii_words_are_found_with_a_typo() -> None:
    assert said("très liquide stocks", "tres liquide") == "très liquide"  # an accent is one edit
    assert said("dès liquide", "des liquide") is None  # in a three-letter token it is not allowed
    assert said("actions très liquides", "très liquidee") == "très liquides"


def test_tokens_keep_decimals_and_drop_trailing_punctuation() -> None:
    assert [t[2] for t in tokens("RSI above 1.5, and (new) highs.")] == [
        "rsi", "above", "1.5", "and", "new", "highs",
    ]  # fmt: skip


def _gaps(sentence: str, covered: list[Span]) -> list[str]:
    return [sentence[s.gap.start : s.gap.end] for s in stretches(sentence, covered) if s.gap]


def test_gaps_hold_a_word_other_than_glue_or_a_connector_and_trim_them() -> None:
    sentence = "liquid stocks and gibberish zzz with high yield"
    covered = [locate(sentence, "liquid stocks"), locate(sentence, "high yield")]
    assert None not in covered
    stretch = stretches(sentence, [c for c in covered if c])
    assert _gaps(sentence, [c for c in covered if c]) == ["gibberish zzz"]
    assert (stretch[0].gap, stretch[1].gap_join, stretch[1].next_join) == (
        None, Join("and", "and"), Join("and", "with"),
    )  # fmt: skip


def test_text_of_connectors_and_punctuation_only_is_no_gap_but_a_join() -> None:
    sentence = "liquid, and stocks"
    found = stretches(sentence, [Span(0, 6), Span(12, 18)])
    assert [s.gap for s in found] == [None, None, None]
    assert found[1].next_join == Join("and", "and")
    assert stretches("", [])[0] == Stretch(None, None, None)


def test_a_sentence_no_part_covers_is_one_gap() -> None:
    assert _gaps("zzz qqq xxx", []) == ["zzz qqq xxx"]


def test_a_negation_between_parts_is_a_gap_with_its_join_never_silent() -> None:
    sentence = "liquid but not overbought and also, except for ETFs"
    covered = [locate(sentence, w) for w in ("liquid", "overbought", "ETFs")]
    first, second = stretches(sentence, [c for c in covered if c])[1:3]
    assert (first.gap, first.gap_join) == (Span(7, 14), Join("and_not", "but not"))
    assert sentence[second.gap.start : second.gap.end] == "except for"
    assert second.gap_join == Join("and_not", "and also, except for")


def test_a_trailing_negation_after_the_last_part_is_a_gap() -> None:
    sentence = "liquid stocks or not"
    last = stretches(sentence, [Span(0, 13)])[-1]
    assert sentence[last.gap.start : last.gap.end] == "or not" and last.gap_join.logic == "and_not"
    assert stretches("liquid stocks and", [Span(0, 13)])[-1].gap is None  # and-type: dropped


def test_an_and_type_connector_before_the_first_part_is_dropped_but_a_negation_is_a_gap() -> None:
    lead = stretches("but liquid", [Span(4, 10)])[0]
    assert (lead.gap, lead.gap_join, lead.next_join) == (None, None, None)
    lead = stretches("not liquid", [Span(4, 10)])[0]
    assert lead.gap == Span(0, 3)


def test_content_beside_a_connector_keeps_the_leading_and_trailing_joins() -> None:
    sentence = "liquid, but cheap and high yield"
    stretch = stretches(sentence, [Span(0, 6), locate(sentence, "high yield")])[1]
    assert (stretch.gap, stretch.gap_join, stretch.next_join) == (
        Span(12, 17), Join("and", "but"), Join("and", "and"),
    )  # fmt: skip
