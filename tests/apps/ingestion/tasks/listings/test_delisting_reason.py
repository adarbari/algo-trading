"""The reason and ``known_from`` rules of a delisting (ADR 0087 decision 4): the precedence of the
8-K items, the -120 / +30 day window, and the Form 25 acceptance rolling to the next session."""

from datetime import UTC, date, datetime, timedelta

import pandas as pd

from algotrade_ingestion.tasks.listings.delisting_reason import judge

LAST_SESSION = date(2020, 3, 18)  # the last bar, a Wednesday


def filing(
    form: str, items: str = "", day: date = LAST_SESSION, hour: int = 14, n: int = 1
) -> dict:
    return {
        "instrument_id": "EQ:X",
        "ts": datetime(day.year, day.month, day.day, hour, tzinfo=UTC),
        "form": form,
        "items": items,
        "accession": f"0001-20-{n:06d}",
    }


def verdict(*rows: dict) -> tuple[str, str, date]:
    frame = pd.DataFrame(rows, columns=["instrument_id", "ts", "form", "items", "accession"])
    got = judge(frame, LAST_SESSION)
    return got.reason, got.reason_source, got.known_from


def test_item_1_03_wins_over_every_other_reason() -> None:
    reason, source, _ = verdict(
        filing("8-K", "3.01", n=1),
        filing("8-K", "2.01,9.01", n=2),
        filing("8-K", "1.03", n=3),
        filing("25", n=4),
    )
    assert reason == "BANKRUPTCY" and source == "0001-20-000003 8-K 1.03"


def test_acquisition_items_beat_a_listing_standard_and_a_form_25() -> None:
    assert verdict(filing("8-K", "3.01", n=1), filing("8-K", "5.01", n=2))[0] == "ACQUIRED"
    assert verdict(filing("8-K/A", "2.01", n=1), filing("25", n=2))[0] == "ACQUIRED"


def test_a_listing_standard_beats_a_form_25_and_a_form_25_alone_is_voluntary() -> None:
    assert verdict(filing("8-K", "3.01", n=1), filing("25", n=2))[0] == "STANDARDS"
    assert verdict(filing("25", n=1))[0] == "VOLUNTARY"
    assert verdict(filing("25/A", n=1))[0] == "VOLUNTARY"  # an amendment is the issuer's too
    assert verdict(filing("25-NSE", n=1))[0] == "UNKNOWN"  # the exchange's notice is no reason


def test_other_items_and_no_filings_are_unknown() -> None:
    assert verdict(filing("8-K", "7.01,9.01"))[:2] == ("UNKNOWN", "")
    assert verdict()[:2] == ("UNKNOWN", "")


def test_the_window_is_120_days_before_and_30_days_after_the_last_trading_day() -> None:
    def reason_on(offset: int) -> str:
        return verdict(filing("8-K", "1.03", day=LAST_SESSION + timedelta(offset)))[0]

    assert reason_on(-120) == "BANKRUPTCY" and reason_on(-121) == "UNKNOWN"
    assert reason_on(30) == "BANKRUPTCY" and reason_on(31) == "UNKNOWN"


def test_known_from_is_the_session_after_the_last_bar_without_a_form_25() -> None:
    assert verdict(filing("8-K", "1.03"))[2] == date(2020, 3, 19)
    assert verdict(filing("8-K", "1.03"), filing("25", day=date(2019, 1, 2)))[2] == date(
        2020, 3, 19
    )


def test_known_from_is_the_session_after_the_form_25_acceptance() -> None:
    before_close = filing("25", day=date(2020, 3, 11), hour=15)  # 11:00 ET: that session
    assert verdict(before_close)[2] == date(2020, 3, 12)
    after_close = filing("25-NSE", day=date(2020, 3, 11), hour=21)  # 17:00 ET: rolls a session
    assert verdict(after_close)[2] == date(2020, 3, 13)
    friday_evening = filing("25", day=date(2020, 3, 13), hour=22)  # rolls over the weekend
    assert verdict(friday_evening)[2] == date(2020, 3, 17)


def test_the_earliest_form_25_sets_known_from() -> None:
    late = filing("25-NSE", day=date(2020, 3, 17), n=1)
    early = filing("25-NSE", day=date(2020, 3, 2), n=2)
    assert verdict(late, early)[2] == date(2020, 3, 3)


def test_known_from_is_never_before_the_filing_that_decided_the_reason() -> None:
    form_25 = filing("25", day=LAST_SESSION - timedelta(10), n=1)  # public long before
    acquired = filing("8-K", "2.01", day=LAST_SESSION + timedelta(5), n=2)  # Mon 2020-03-23
    reason, _, known = verdict(form_25, acquired)
    assert reason == "ACQUIRED" and known == date(2020, 3, 24)  # after the 8-K, not the Form 25
    # with no notice: after the later of the last bar and the deciding filing
    assert verdict(filing("8-K", "1.03", day=LAST_SESSION - timedelta(40)))[2] == date(2020, 3, 19)
    assert verdict(filing("8-K", "1.03", day=LAST_SESSION + timedelta(5)))[2] == date(2020, 3, 24)
    # a deciding filing accepted after the close is public from the next session
    late = filing("8-K", "1.03", day=date(2020, 3, 18), hour=22)
    assert verdict(late)[2] == date(2020, 3, 20)


def test_notices_include_the_amendments() -> None:
    assert verdict(filing("25/A", day=date(2020, 3, 11), hour=15))[2] == date(2020, 3, 12)
    assert verdict(filing("25-NSE/A", day=date(2020, 3, 11), hour=15))[2] == date(2020, 3, 12)
