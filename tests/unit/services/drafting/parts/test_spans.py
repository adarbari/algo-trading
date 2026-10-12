"""Where a part's words are in the sentence: exact, ignoring case, with a typo; repeated words are
found in order; no match is ``None``; a short or numeric token is never fuzzy; offsets convert to
UTF-16 code units (a non-ASCII sentence slices back to the same words in a browser); the gaps."""

from algotrade.services.drafting.parts.spans import Span, gaps, locate, tokens, utf16

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


def test_gaps_hold_a_word_other_than_a_connector_and_trim_the_connectors() -> None:
    sentence = "liquid stocks and gibberish zzz with high yield"
    covered = [locate(sentence, "liquid stocks"), locate(sentence, "high yield")]
    assert None not in covered
    found = [sentence[g.start : g.end] for g in gaps(sentence, [c for c in covered if c])]
    assert found == ["gibberish zzz"]  # "and" and "with" at the edges are connectors


def test_text_of_connectors_and_punctuation_only_is_no_gap() -> None:
    sentence = "liquid, and stocks"
    assert gaps(sentence, [Span(0, 6), Span(12, 18)]) == []
    assert gaps("", []) == []


def test_a_sentence_no_part_covers_is_one_gap() -> None:
    assert [Span(0, 11)] == gaps("zzz qqq xxx", [])
