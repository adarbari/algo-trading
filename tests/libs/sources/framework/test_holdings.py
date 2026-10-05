"""The shared holdings shape every issuer adapter returns."""

import pytest

from algotrade_sources.framework.holdings import (
    HOLDING_COLUMNS,
    clean_text,
    fraction,
    funds_frame,
    holding_ticker,
    holdings_frame,
    is_cusip,
    is_position,
    number,
)


@pytest.mark.parametrize(
    ("raw", "ticker"),
    [
        ("NVDA", "NVDA"),
        (" aapl ", "AAPL"),
        ("BF B", "BF.B"),  # iShares prints the share class after a space
        ("BRK/B", "BRK.B"),
        ("BRK-B", "BRK.B"),
        ("BRK.B", "BRK.B"),
        ("-", None),
        ("CASH_USD", None),
        ("A000660", None),  # a foreign exchange code
        ("", None),
        (None, None),
        (float("nan"), None),
    ],
)
def test_tickers_use_the_universe_style_or_nothing(raw: object, ticker: str | None) -> None:
    assert holding_ticker(raw) == ticker


def test_numbers_read_the_ways_issuers_print_them() -> None:
    assert number("1,234.5") == 1234.5
    assert number("9.39%") == 9.39
    assert number("$869,444,904.90") == 869444904.9
    assert number(3) == 3.0 and number(None) is None and number("n/a") is None
    assert number(True) is None
    assert fraction("8.44") == 0.0844 and fraction("-0.10") == -0.001
    assert fraction("-") is None and fraction(None) is None  # unreadable is not 0


def test_text_placeholders_are_missing() -> None:
    assert clean_text(" Apple ") == "Apple"
    assert clean_text("-") is None and clean_text("Unassigned") is None and clean_text(None) is None


def test_the_frame_is_sorted_by_weight_and_drops_unreadable_lines() -> None:
    rows = [
        {"holding_name": "B", "weight": 0.1, "us_listed": False},
        {"holding_name": "A", "weight": 0.3, "us_listed": True, "holding_symbol": "A"},
        {"holding_name": None, "weight": 0.5, "us_listed": False},
        {"holding_name": "C", "weight": 0.1, "us_listed": False},
        {"holding_name": "D", "weight": -0.02, "us_listed": False},
    ]
    frame = holdings_frame(rows)
    assert tuple(frame.columns) == HOLDING_COLUMNS
    assert list(frame["holding_name"]) == ["A", "B", "C", "D"]  # ties keep the file's order
    assert str(frame["weight"].dtype) == "float64" and str(frame["us_listed"].dtype) == "bool"


def test_lines_rank_by_the_size_of_their_weight_and_unreadable_ones_are_dropped() -> None:
    rows = [
        {"holding_name": "Long", "weight": 0.2, "us_listed": False},
        {"holding_name": "Swap", "weight": -0.9, "us_listed": False},
        {"holding_name": "Broken", "weight": fraction("n/a"), "us_listed": False},
        {"holding_name": "Short", "weight": -0.3, "us_listed": False},
    ]
    frame = holdings_frame(rows)
    assert list(frame["holding_name"]) == ["Swap", "Short", "Long"]  # Broken is not a 0% line
    assert list(frame["weight"]) == [-0.9, -0.3, 0.2]  # the sign is kept


def test_every_cash_label_is_not_a_position_and_a_cusip_starts_with_a_digit() -> None:
    labels = [
        "Cash Collateral and Margins",
        "Cash Collateral and Margin",
        "Cash and/or Derivatives",
    ]
    assert not any(is_position(k) for k in labels)
    ids = ("037833100", "87971M103", "G54950103", "US0378331005", "CASH_USD", None)
    # A CUSIP or a CINS (Linde): nine characters; an ISIN, a cash id and a blank are neither.
    assert [is_cusip(c) for c in ids] == [True, True, True, False, False, False]


def test_cash_futures_and_fx_lines_are_not_positions() -> None:
    kinds = ["Equity", "Fixed Income", "Cash", "Money Market", "Futures", "FX", "Derivative", None]
    assert [is_position(k) for k in kinds] == [True, True, False, False, False, False, False, True]


def test_the_directory_frame_is_one_sorted_row_per_ticker() -> None:
    frame = funds_frame([("XLK", "Tech"), ("DIA", "Dow"), ("XLK", "Tech again")])
    assert list(frame["symbol"]) == ["DIA", "XLK"]
