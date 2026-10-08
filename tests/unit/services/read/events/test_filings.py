"""An instrument's 8-Ks in a trailing window of months, among the rows known on or before the
session, newest first, each labelled by its first item; a company with none known is NO_ROW."""

from datetime import UTC, date, datetime

import pytest

from algotrade.services.read.events import filings
from algotrade.services.read.events.filings import item_label, load_filings, months_before
from algotrade.services.read.values import UnknownCode
from tests.unit.services.read.events.conftest import D1, context, store_with


def test_the_window_known_by_the_session_newest_first() -> None:
    found, gaps = load_filings(context(store_with()), ["EQ:AAA"], 24)
    aaa = found["EQ:AAA"]
    assert [(f.accepted, f.label, f.items) for f in aaa] == [
        (datetime(2026, 9, 15, 13, tzinfo=UTC), "Management change", ("5.02",)),
        (datetime(2026, 7, 30, 20, 10, tzinfo=UTC), "Results", ("2.02", "9.01")),
    ]  # 2024-02-01 is before the window; 2026-10-02 was accepted after the session
    assert (aaa[1].form, aaa[1].filing_date, aaa[1].known_from) == (
        "8-K", date(2026, 7, 30), date(2026, 7, 30),
    )  # fmt: skip
    assert gaps == {}
    longer, _ = load_filings(context(store_with()), ["EQ:AAA"], 36)
    assert len(longer["EQ:AAA"]) == 3


def test_a_company_with_no_filing_known_is_unknown() -> None:
    found, gaps = load_filings(context(store_with()), ["EQ:AAA", "EQ:BBB"], 24)
    assert found["EQ:BBB"] == ()
    assert gaps["EQ:BBB"].code is UnknownCode.NO_ROW
    assert "event-study scope only" in gaps["EQ:BBB"].cause.text
    assert "EQ:AAA" not in gaps


def test_no_instruments_read_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """An ETF-only event study asks for no stocks: no read of the filing table (whose every
    partition an ``ALL_TIME`` read would open to keep no row)."""

    def no_read(*_: object, **__: object) -> None:
        raise AssertionError("read_events called for no instruments")

    monkeypatch.setattr(filings, "read_events", no_read)
    assert load_filings(context(store_with()), [], 24) == ({}, {})


def test_labels_and_months() -> None:
    assert item_label(("2.02", "9.01"), "8-K") == "Results"
    assert item_label(("7.01",), "8-K") == "Guidance / Reg FD"
    assert item_label(("6.05",), "8-K") == "Item 6.05"
    assert item_label((), "8-K/A") == "8-K/A"
    assert months_before(D1, 24) == date(2024, 10, 1)
    assert months_before(date(2026, 3, 31), 1) == date(2026, 2, 28)
    assert months_before(date(2026, 1, 15), 13) == date(2024, 12, 15)
