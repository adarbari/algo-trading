"""``earnings_reaction_session@v1``: the session a report's reaction lands on, from the time of
day the calendar row known by the session gave, point in time (F10)."""

from datetime import date

import pandas as pd
import pytest

from algotrade.features.rollups.corporate import earnings, earnings_reaction_session
from tests.helpers.stored_frames import stamped

STORED = date(2026, 10, 30)
A = "EQ:A"


def _events(rows: list[tuple[str, date, str, date]], source: str = "test") -> pd.DataFrame:
    """(instrument, report date, time, known_from) rows, all stored on ``STORED``."""
    frame = [
        {
            "instrument_id": i,
            "ts": pd.Timestamp(d, tz="UTC"),
            "time": t,
            "known_from": k,
            "reported": k < STORED,
        }
        for i, d, t, k in rows
    ]
    return stamped(frame, STORED, "r", source=source)


def _compute(rows: list[tuple[str, date, str, date]], session: date) -> pd.DataFrame:
    return earnings_reaction_session.compute({earnings.EVENTS: _events(rows)}, session, None)


def _row(frame: pd.DataFrame, iid: str = A) -> pd.Series:
    return frame.set_index("instrument_id").loc[iid]


def test_a_pre_market_report_reacts_on_its_own_session_and_an_after_hours_one_the_next() -> None:
    e = date(2026, 10, 21)  # Wednesday
    pre = _row(_compute([(A, e, "pre_market", e)], date(2026, 10, 23)))
    assert pre["reaction_report_time"] == "pre_market"
    assert pre["reaction_session_date"] == e and pre["sessions_since_reaction_session"] == 2
    after = _row(_compute([(A, e, "after_hours", e)], date(2026, 10, 23)))
    assert after["reaction_session_date"] == date(2026, 10, 22)
    assert after["sessions_since_reaction_session"] == 1
    assert after["reaction_session_status"] == "OK"


def test_an_after_hours_report_made_today_is_pending_and_a_pre_market_one_is_not() -> None:
    e = date(2026, 10, 21)
    after = _row(_compute([(A, e, "after_hours", e)], e))
    assert after["reaction_session_status"] == "PENDING" and pd.isna(after["reaction_session_date"])
    pre = _row(_compute([(A, e, "pre_market", e)], e))
    assert pre["reaction_session_status"] == "OK" and pre["sessions_since_reaction_session"] == 0


def test_an_after_hours_report_before_a_weekend_reacts_on_monday() -> None:
    friday = date(2026, 10, 23)
    got = _row(_compute([(A, friday, "after_hours", friday)], date(2026, 10, 26)))
    assert got["reaction_session_date"] == date(2026, 10, 26)
    assert got["sessions_since_reaction_session"] == 0


@pytest.mark.parametrize("time", ["unknown", "intraday", None])
def test_an_unknown_time_is_skipped_never_guessed(time: str | None) -> None:
    e = date(2026, 10, 21)
    got = _row(_compute([(A, e, time, e)], date(2026, 10, 23)))
    assert got["reaction_session_status"] == "UNKNOWN_TIME"
    assert got["reaction_report_time"] == "unknown"
    assert pd.isna(got["reaction_session_date"]) and pd.isna(got["sessions_since_reaction_session"])


def test_a_report_known_after_the_session_and_an_8k_intraday_row_are_never_read() -> None:
    older, newer = date(2026, 7, 22), date(2026, 10, 21)
    rows = [(A, older, "after_hours", older), (A, newer, "pre_market", date(2026, 10, 28))]
    session = date(2026, 10, 23)  # the newer row is known only on 10-28
    got = _row(_compute(rows, session))
    assert got["reaction_session_date"] == date(2026, 7, 23)  # the older report's
    eight_k = _events([(A, newer, "intraday", date(2026, 10, 28))], source=earnings.SEC_8K_SOURCE)
    both = pd.concat([_events(rows[:1]), eight_k], ignore_index=True)
    out = earnings_reaction_session.compute({earnings.EVENTS: both}, date(2026, 10, 30), None)
    assert _row(out)["reaction_session_date"] == date(2026, 7, 23)  # the 8-K row is not a report
    full = _row(_compute(rows, date(2026, 10, 30)))
    assert full["reaction_session_date"] == newer  # known by then: the newer report counts


def test_truncation_invariance_and_a_name_without_a_report_has_no_row() -> None:
    e = date(2026, 10, 21)
    session = date(2026, 10, 23)
    base = _compute([(A, e, "pre_market", e)], session)
    later = _compute(
        [(A, e, "pre_market", e), (A, date(2026, 10, 29), "pre_market", date(2026, 10, 29))],
        session,
    )
    pd.testing.assert_frame_equal(base, later)
    assert (
        set(_compute([("EQ:B", date(2026, 11, 20), "pre_market", e)], session)["instrument_id"])
        == set()
    )
