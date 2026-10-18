"""``schedule``: a schedule and a holding period in plain words, with the glossary term that
explains them."""

import pytest

from algotrade.services.read.guide.edges.schedule import (
    holding_band,
    holding_text,
    trigger_term,
    trigger_text,
)

TERMS = {
    "calendar_opex_week",
    "event_class_filing_8k",
    "event_class_filing_8k_4_02",
    "event_class_index_change",
    "market_trigger_vix_spike",
}


@pytest.mark.parametrize(
    ("schedule", "text", "term"),
    [
        ("every_session", "Every trading day", None),
        ("month_end", "Once a month, at the month end", None),
        ("calendar:opex_week", "In option-expiration week", "calendar_opex_week"),
        ("on_event:index_change", "When the S&P 500 changes a member", "event_class_index_change"),
        (
            "on_event:index_change:deletion",
            "When the S&P 500 changes a member (a name leaves)",
            "event_class_index_change",
        ),
        (
            "on_event:filing_8k:4.02",
            "When a company files an 8-K (Item 4.02)",
            "event_class_filing_8k_4_02",
        ),
        ("on_market:vix_spike", "When the VIX spikes", "market_trigger_vix_spike"),
        ("on_event:earnings_reaction", "After a company reports earnings", None),
    ],
)
def test_a_trigger_in_words(schedule: str, text: str, term: str | None) -> None:
    assert trigger_text(schedule) == text
    assert trigger_term(schedule, TERMS) == term


def test_a_term_that_is_not_written_is_not_named() -> None:
    assert trigger_term("calendar:opex_week", set()) is None


@pytest.mark.parametrize(
    ("horizons", "text", "band"),
    [
        ((1,), "1 session", "short"),
        ((5,), "5 sessions", "short"),
        ((5, 21), "5 or 21 sessions", "medium"),
        ((5, 10, 63), "5, 10 or 63 sessions", "long"),
        ((21,), "21 sessions", "medium"),
        ((22,), "22 sessions", "long"),
    ],
)
def test_holding_and_its_band(horizons: tuple[int, ...], text: str, band: str) -> None:
    assert holding_text(horizons) == text
    assert holding_band(horizons) == band
