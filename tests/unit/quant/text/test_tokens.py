"""The pinned tokeniser: NFKC and casefold, runs of two or more letters, digits dropped, the
written stop list removed, no stemming, a fixed result for a fixed text."""

from algotrade.quant.text.tokens import STOPWORDS, term_counts, tokenize


def test_tokens_are_casefolded_letter_runs_of_two_or_more_without_digits_or_stop_words() -> None:
    text = "The Company's 2025 revenue, a risk: R&D costs of $5.2M rose 10%; Inflation matters."
    assert tokenize(text) == [
        "company", "revenue", "risk", "costs", "rose", "inflation", "matters",
    ]  # fmt: skip


def test_no_stemming_and_normalisation_folds_compatibility_forms() -> None:
    assert tokenize("risks risk risking") == ["risks", "risk", "risking"]
    assert tokenize("\N{FULLWIDTH LATIN CAPITAL LETTER R}isk") == [
        "risk"
    ]  # a full-width letter folds to ascii


def test_counts_are_raw_term_frequencies() -> None:
    assert dict(term_counts("risk risk Risk market")) == {"risk": 3, "market": 1}
    assert not term_counts("the of 123 a")


def test_the_stop_list_is_pinned() -> None:
    assert len(STOPWORDS) == 122 and "the" in STOPWORDS and "risk" not in STOPWORDS
    assert all(w.isascii() and w.islower() for w in STOPWORDS)
