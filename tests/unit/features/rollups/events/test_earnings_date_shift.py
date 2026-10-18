"""``earnings_date_shift@v1``: the next report date against the year-ago report plus 364 days,
the direction when it moved a week or more, and the session the date was first stored (the
anchor), point in time; the history starts with the first stored calendar snapshot."""

from datetime import date

import pandas as pd

from algotrade.features.rollups.corporate import earnings
from algotrade.features.rollups.events import earnings_date_shift as eds
from tests.helpers.stored_frames import stamped

BACKFILL = date(2026, 9, 1)  # last year's reports, history rows known from their own day
FIRST, SECOND = date(2026, 9, 15), date(2026, 9, 22)  # calendar snapshots (forecasts)
YEAR_AGO = date(2025, 10, 20)  # a Monday: +364 days is Monday 2026-10-19


def _rows(spec: list[tuple[str, date, date, date | None]]) -> pd.DataFrame:
    """(instrument, report date, stored session, known_from; None: a forecast) rows."""
    parts = []
    for stored in sorted({s for _, _, s, _ in spec}):
        rows = [
            {
                "instrument_id": i,
                "ts": pd.Timestamp(d, tz="UTC"),
                "time": "unknown",
                "known_from": k if k is not None else stored,
                "reported": k is not None,
            }
            for i, d, s, k in spec
            if s == stored
        ]
        parts.append(stamped(rows, stored, f"r-{stored}"))
    return pd.concat(parts, ignore_index=True)


def _world() -> pd.DataFrame:
    history = [(f"EQ:{i}", YEAR_AGO, BACKFILL, YEAR_AGO) for i in "ABCD"]
    first = [("EQ:D", date(2026, 10, 26), FIRST, None), ("EQ:C", date(2026, 10, 19), FIRST, None)]
    second = [
        ("EQ:A", date(2026, 10, 29), SECOND, None),  # ten days later than 10-19
        ("EQ:B", date(2026, 10, 12), SECOND, None),  # a week earlier
        ("EQ:C", date(2026, 10, 19), SECOND, None),  # as a year ago
        ("EQ:D", date(2026, 10, 26), SECOND, None),  # a week later, but first stored at FIRST
    ]
    return _rows(history + first + second)


def _at(session: date) -> pd.DataFrame:
    out = eds.compute({earnings.EVENTS: _world()}, session, None)
    return out.set_index("instrument_id")


def test_a_date_a_week_or_more_from_last_years_is_an_event_from_the_session_it_was_stored() -> None:
    out = _at(date(2026, 9, 23))
    assert out.at["EQ:A", "earnings_date_shift_days"] == 10
    assert out.at["EQ:A", "earnings_shift_direction"] == "later"
    assert out.at["EQ:A", "earnings_shift_known_date"] == SECOND
    assert out.at["EQ:A", "sessions_since_earnings_shift"] == 1
    assert out.at["EQ:B", "earnings_shift_direction"] == "earlier"
    assert out.at["EQ:B", "earnings_date_shift_days"] == -7


def test_an_unshifted_date_has_a_shift_but_no_direction_and_no_event() -> None:
    out = _at(date(2026, 9, 23))
    assert out.at["EQ:C", "earnings_date_shift_days"] == 0
    assert pd.isna(out.at["EQ:C", "earnings_shift_direction"])
    assert pd.isna(out.at["EQ:C", "sessions_since_earnings_shift"])


def test_a_date_stored_at_the_first_snapshot_is_not_an_event() -> None:
    """The vendor backfill carries no time: a date first stored at the first snapshot (or
    before) says nothing about when it became known, so its shift is no event."""
    out = _at(date(2026, 9, 23))
    assert out.at["EQ:D", "earnings_date_shift_days"] == 7
    assert pd.isna(out.at["EQ:D", "earnings_shift_direction"])


def test_a_date_stored_after_the_session_is_not_known_by_it() -> None:
    out = _at(date(2026, 9, 17))  # before the second snapshot: A's date is not stored yet
    assert "EQ:A" in out.index and pd.isna(out.at["EQ:A", "earnings_date_shift_days"])
    assert pd.isna(out.at["EQ:A", "earnings_shift_direction"])


def test_the_count_grows_with_the_session() -> None:
    assert _at(date(2026, 9, 28)).at["EQ:A", "sessions_since_earnings_shift"] == 4
