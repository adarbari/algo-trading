"""``earnings_expected@v1``: SCHEDULED, PRIOR_YEAR or UNKNOWN, point in time (ED4e)."""

from datetime import date

import pandas as pd

from algotrade.features.rollups.corporate import earnings, earnings_expected
from tests.helpers.stored_frames import stamped

STORED = date(2026, 10, 2)  # the backfill's own session: every past report is a history row


def _events(rows: list[tuple[str, date, date]], stored: date = STORED) -> pd.DataFrame:
    """(instrument, report date, known_from) rows, all stored on ``stored``."""
    frame = [
        {
            "instrument_id": i,
            "ts": pd.Timestamp(d, tz="UTC"),
            "time": "unknown",
            "known_from": k,
            "reported": k < stored,
        }
        for i, d, k in rows
    ]
    return stamped(frame, stored, "r")


def _at(rows: pd.DataFrame, session: date) -> dict[str, tuple[object, str, object]]:
    out = earnings_expected.compute({earnings.EVENTS: rows}, session, None)
    return {
        r.instrument_id: (r.expected_report_date, r.expected_basis, r.sessions_to_expected_report)
        for r in out.itertuples()
    }


def _nulls(value: object) -> object:
    return None if pd.isna(value) else value


def test_prior_year_is_the_year_ago_report_plus_364_days() -> None:
    year_ago = date(2025, 10, 20)  # a Monday: +364 days is Monday 2026-10-19
    rows = _events([("EQ:A", year_ago, year_ago), ("EQ:A", date(2026, 7, 20), date(2026, 7, 20))])
    got = _at(rows, date(2026, 10, 5))
    assert got["EQ:A"][:2] == (date(2026, 10, 19), "PRIOR_YEAR")
    assert got["EQ:A"][2] == 10  # Oct 6-9, 12-16, 19


def test_scheduled_wins_over_prior_year_and_counts_sessions() -> None:
    rows = _events(
        [
            ("EQ:A", date(2025, 10, 20), date(2025, 10, 20)),
            ("EQ:A", date(2026, 10, 14), date(2026, 10, 1)),  # a calendar forecast known 10-01
        ]
    )
    got = _at(rows, date(2026, 10, 5))
    assert got["EQ:A"] == (date(2026, 10, 14), "SCHEDULED", 7)  # Oct 6-9, 12-14


def test_unknown_when_neither_a_scheduled_date_nor_a_usable_anniversary() -> None:
    old = date(2025, 9, 1)  # anniversary 2026-08-31 is already past on 10-05
    got = _at(_events([("EQ:A", old, old)]), date(2026, 10, 5))
    date_, basis, sessions = got["EQ:A"]
    assert basis == "UNKNOWN" and _nulls(date_) is None and _nulls(sessions) is None


def test_a_row_known_after_the_session_never_makes_it_scheduled() -> None:
    # The Nasdaq backfill stores each report known from its own day, long after the day.
    rows = _events([("EQ:A", date(2026, 10, 14), date(2026, 10, 14))], stored=date(2026, 10, 20))
    assert _at(rows, date(2026, 10, 5)) == {}  # nothing known: no row, never SCHEDULED
    seen = _at(rows, date(2026, 10, 14))
    assert seen["EQ:A"][:2] == (date(2026, 10, 14), "SCHEDULED")  # known on its own day


def test_calendar_counting_skips_holidays_and_weekends() -> None:
    rows = _events([("EQ:A", date(2026, 11, 27), date(2026, 11, 1))], stored=date(2026, 11, 1))
    got = _at(rows, date(2026, 11, 24))  # Thanksgiving 11-26 is closed: 11-25, 11-27
    assert got["EQ:A"][2] == 2


def test_truncation_invariance() -> None:
    reports = [
        ("EQ:A", date(2025, 10, 20), date(2025, 10, 20)),
        ("EQ:A", date(2026, 1, 21), date(2026, 1, 21)),
        ("EQ:A", date(2026, 4, 21), date(2026, 4, 21)),
        ("EQ:A", date(2026, 7, 21), date(2026, 7, 21)),
        ("EQ:A", date(2026, 10, 20), date(2026, 10, 20)),  # the actual future date
        ("EQ:B", date(2025, 11, 4), date(2025, 11, 4)),
        ("EQ:B", date(2026, 11, 3), date(2026, 11, 3)),
        ("EQ:C", date(2026, 10, 12), date(2026, 9, 30)),  # a forecast
    ]
    full = _events(reports, stored=date(2026, 12, 1))
    for session in (date(2026, 9, 30), date(2026, 10, 5), date(2026, 10, 19), date(2026, 10, 20)):
        known = full[pd.to_datetime(full["known_from"]).dt.date <= session]
        assert _at(full, session) == _at(known, session)  # rows known later change nothing


def test_an_already_reported_quarter_is_not_expected_again() -> None:
    rows = _events(
        [
            ("EQ:A", date(2025, 1, 30), date(2025, 1, 30)),
            ("EQ:A", date(2025, 4, 30), date(2025, 4, 30)),
            ("EQ:A", date(2026, 1, 25), date(2026, 1, 25)),  # this year's, early
        ]
    )
    got = _at(rows, date(2026, 1, 26))  # no phantom 2026-01-29: the next anchor is April
    assert got["EQ:A"][:2] == (date(2026, 4, 29), "PRIOR_YEAR")


def test_an_expectation_over_100_days_out_is_unknown() -> None:
    old = date(2025, 10, 20)  # anniversary 2026-10-19 is 197 days after 2026-04-05
    got = _at(_events([("EQ:A", old, old)]), date(2026, 4, 5))
    assert got["EQ:A"][1] == "UNKNOWN" and _nulls(got["EQ:A"][0]) is None


def test_a_holiday_anniversary_rolls_to_the_next_session() -> None:
    year_ago = date(2025, 11, 27)  # +364 = 2026-11-26, Thanksgiving: closed
    got = _at(_events([("EQ:A", year_ago, year_ago)]), date(2026, 11, 23))
    assert got["EQ:A"] == (date(2026, 11, 27), "PRIOR_YEAR", 3)  # sessions 24, 25, 27
