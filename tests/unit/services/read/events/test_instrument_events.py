"""``InstrumentEvents`` for one session: the events ahead (own earnings by catalogue name, the
macro releases known by the session, the market-structure days), the filings, the expiry
ladder and the fund reference; every part not known for the session is a gap with its
UNKNOWN, never an older partition or a later row."""

from datetime import date

from algotrade.services.read.events.ahead import (
    MACRO_RELEASE,
    MARKET_STRUCTURE,
    OWN_EARNINGS,
    REFERENCE_EARNINGS,
)
from algotrade.services.read.events.instrument_events import load_instrument_events
from algotrade.services.read.events.reference import FundReference
from algotrade.services.read.values import UnknownCode
from tests.unit.services.read.events.conftest import D0, D1, REPORT, context, store_with


def _gaps(found: object) -> dict[str, UnknownCode]:
    return {g.part: g.unknown.code for g in found.gaps}  # type: ignore[attr-defined]


def test_a_stock_for_the_session() -> None:
    found = load_instrument_events(context(store_with()), ["EQ:AAA"])["EQ:AAA"]
    assert (found.session, found.days, found.months) == (D1, 90, 24)
    assert [(e.date, e.kind, e.label) for e in found.ahead] == [
        (date(2026, 10, 14), MACRO_RELEASE, "CPI"),
        (date(2026, 10, 16), MARKET_STRUCTURE, "Monthly expiry"),
        (REPORT, OWN_EARNINGS, "Earnings"),
        (date(2026, 10, 29), MACRO_RELEASE, "GDP"),
        (date(2026, 11, 20), MARKET_STRUCTURE, "Monthly expiry"),
        (date(2026, 12, 18), MARKET_STRUCTURE, "Quarterly expiry"),
    ]
    assert [e.expiry for e in found.ahead] == [
        False,
        True,
        False,
        False,
        True,
        True,
    ]  # expiry days only
    cpi, _, report = found.ahead[:3]
    assert (cpi.time, cpi.name, cpi.subject_id, cpi.source, cpi.known_from) == (
        "08:30 ET", "CPI release", "MACRO:CPI", "fred", D0,
    )  # fmt: skip
    assert (report.time, report.name, report.subject_id, report.known_from) == (
        "after_hours", "Reports after the close (confirmed)", "EQ:AAA", None,
    )  # fmt: skip
    assert report.source == "rollup.earnings@v1.next_earnings_date"
    assert found.ahead[1].time == "close" and found.ahead[1].subject_id is None
    assert [f.label for f in found.filings] == ["Management change", "Results"]
    assert found.reference is None  # a stock: not applicable, and no gap for it
    assert found.gaps == ()


def test_the_window_and_the_older_partition() -> None:
    """``days`` cuts the list; D1's earnings partition is read, never D0's (Oct 2)."""
    found = load_instrument_events(context(store_with()), ["EQ:AAA"], days=14)["EQ:AAA"]
    assert [e.date for e in found.ahead] == [date(2026, 10, 14)]
    assert REPORT in {e.date for rung in found.ladder for e in rung.spans}  # the ladder: 90 days


def test_known_from_bounds_the_macro_calendar() -> None:
    """As of D0 the PPI and the first GDP date are still scheduled (their released and moved
    versions came on D1); the FOMC date published after the session is never shown."""
    found = load_instrument_events(context(store_with(), D0), ["EQ:AAA"])["EQ:AAA"]
    macro = [(e.label, e.date) for e in found.ahead if e.kind == MACRO_RELEASE]
    assert macro == [
        ("PPI", date(2026, 10, 1)),
        ("GDP", date(2026, 10, 7)),
        ("CPI", date(2026, 10, 14)),
    ]
    later = load_instrument_events(context(store_with()), ["EQ:AAA"])["EQ:AAA"]
    assert "FOMC" not in {e.label for e in later.ahead}
    own = next(e for e in found.ahead if e.kind == OWN_EARNINGS)  # D0's own partition
    assert (own.date, own.time, own.name) == (
        date(2026, 10, 2), "pre_market", "Reports before the open (not confirmed)",
    )  # fmt: skip


def test_a_leveraged_fund_inherits_its_references_earnings() -> None:
    found = load_instrument_events(context(store_with()), ["EQ:AAAU"])["EQ:AAAU"]
    assert found.reference == FundReference("EQ:AAA", "AAA", "single_stock", "holdings", "LINKED")
    [report] = [e for e in found.ahead if e.kind == REFERENCE_EARNINGS]
    assert (report.date, report.label, report.subject_id) == (REPORT, "AAA earnings", "EQ:AAA")
    assert report.name == "AAA reports after the close (confirmed)"
    assert found.filings == ()
    assert _gaps(found) == {
        OWN_EARNINGS: UnknownCode.NOT_APPLICABLE,  # a fund has no earnings of its own
        "filings": UnknownCode.NOT_APPLICABLE,
        "ladder": UnknownCode.NO_ROW,  # the session's chain has no AAAU quotes
    }


def test_a_session_with_nothing_stored_is_unknown_not_an_older_partition() -> None:
    day = date(2026, 10, 2)  # asked for: no partition of anything, D1's are older
    found = load_instrument_events(context(store_with(), day), ["EQ:AAA", "EQ:AAAU"])
    aaa, fund = found["EQ:AAA"], found["EQ:AAAU"]
    assert OWN_EARNINGS not in {e.kind for e in aaa.ahead}
    assert _gaps(aaa) == {
        OWN_EARNINGS: UnknownCode.NO_PARTITION,
        "ladder": UnknownCode.NO_PARTITION,
    }
    assert aaa.ladder == ()
    assert fund.reference is None and _gaps(fund)["reference"] is UnknownCode.NO_PARTITION
    # event tables are read by known_from, not by partition: the 8-K public on the 2nd shows
    assert [f.label for f in aaa.filings] == ["Material agreement", "Management change", "Results"]


def test_an_etf_and_an_unknown_instrument() -> None:
    found = load_instrument_events(context(store_with()), ["EQ:ETFX", "EQ:ZZZ"])
    assert set(found) == {"EQ:ETFX"}  # not in the reference snapshot: no such instrument
    etf = found["EQ:ETFX"]
    assert etf.reference is None
    assert _gaps(etf) == {
        OWN_EARNINGS: UnknownCode.NOT_APPLICABLE,
        "filings": UnknownCode.NOT_APPLICABLE,
        "ladder": UnknownCode.NO_ROW,
    }
    assert load_instrument_events(context(store_with()), ["EQ:ZZZ"]) == {}


def test_the_macro_calendar_with_nothing_known_by_the_session_is_a_gap() -> None:
    found = load_instrument_events(context(store_with(), date(2026, 9, 1)), ["EQ:AAA"])
    gap = next(g for g in found["EQ:AAA"].gaps if g.part == MACRO_RELEASE)
    assert gap.instrument_id is None and gap.unknown.code is UnknownCode.NO_PARTITION
    assert (
        "events/macro_release has no release dates known by the session 2026-09-01"
        in gap.unknown.detail
    )


def test_no_future_release_known_by_the_session_is_a_gap() -> None:
    """As of Nov 15 every stored release is in the past: the calendar is not current (NO_ROW),
    not "no releases ahead"."""
    found = load_instrument_events(context(store_with(), date(2026, 11, 15)), ["EQ:AAA"])
    gap = next(g for g in found["EQ:AAA"].gaps if g.part == MACRO_RELEASE)
    assert gap.unknown.code is UnknownCode.NO_ROW
    assert "no future release dates known by the session 2026-11-15" in gap.unknown.detail
    assert MACRO_RELEASE not in {e.kind for e in found["EQ:AAA"].ahead}
