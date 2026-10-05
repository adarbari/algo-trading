"""``earnings@v1``: next / last dates as known on each session (stored snapshots on or before
it), moved dates, report time, and sessions to the report across holidays."""

from datetime import date

import pandas as pd

from algotrade.features.framework.runner import compute_one, compute_sessions
from algotrade.features.rollups.corporate import earnings
from tests.helpers.rollup_store import store, write_earnings

GROUP = earnings.GROUP


def row(frame: pd.DataFrame | None, iid: str) -> dict[str, object]:
    assert frame is not None
    return frame.set_index("instrument_id").loc[iid].to_dict()


def calendar() -> tuple[object, object]:
    writer, reader = store()
    # 2026-09-01 knew: A reports 09-15 before the open, C on 10-05.
    write_earnings(
        writer,
        date(2026, 9, 1),
        [("EQ:A", date(2026, 9, 15), "pre_market"), ("EQ:C", date(2026, 10, 5), "after_hours")],
    )
    # 2026-10-01 covers 10-01..11-30: C moved to 10-08; A next reports after Thanksgiving.
    write_earnings(
        writer,
        date(2026, 10, 1),
        [
            ("EQ:C", date(2026, 10, 8), "after_hours"),
            ("EQ:A", date(2026, 11, 30), "time-not-supplied"),
        ],
    )
    return writer, reader


def test_next_and_last_as_known_on_the_session() -> None:
    _, reader = calendar()
    early = compute_one(reader, GROUP, date(2026, 9, 10)).frame  # only the 09-01 snapshot
    assert row(early, "EQ:C")["next_earnings_date"] == date(2026, 10, 5)
    a = row(early, "EQ:A")
    assert (a["next_earnings_date"], a["earnings_time"], a["days_to_earnings"]) == (
        date(2026, 9, 15),
        "pre",
        3,
    )
    late = compute_one(reader, GROUP, date(2026, 10, 2)).frame
    c = row(late, "EQ:C")
    assert (c["next_earnings_date"], c["earnings_time"]) == (date(2026, 10, 8), "post")
    assert pd.isna(c["last_earnings_date"])  # 10-05 was moved, never happened
    a = row(late, "EQ:A")
    assert (a["last_earnings_date"], a["earnings_time"]) == (date(2026, 9, 15), "unknown")
    assert pd.isna(a["date_confirmed"])  # the source does not say


def test_days_to_earnings_skip_holidays_and_count_today_as_zero() -> None:
    _, reader = calendar()
    nov = row(compute_one(reader, GROUP, date(2026, 11, 20)).frame, "EQ:A")
    assert nov["days_to_earnings"] == 5  # 23, 24, 25, (Thanksgiving), 27, 30
    today = row(compute_one(reader, GROUP, date(2026, 10, 8)).frame, "EQ:C")
    assert today["days_to_earnings"] == 0 and today["next_earnings_date"] == date(2026, 10, 8)
    after = row(compute_one(reader, GROUP, date(2026, 10, 9)).frame, "EQ:C")
    assert pd.isna(after["next_earnings_date"]) and after["last_earnings_date"] == date(2026, 10, 8)


def test_no_snapshot_yet_is_no_input_and_backfill_matches() -> None:
    _, reader = calendar()
    assert compute_one(reader, GROUP, date(2026, 8, 31)).no_input
    days = [date(2026, 9, 10), date(2026, 10, 2), date(2026, 11, 20)]
    for result in compute_sessions(reader, GROUP, days):
        alone = compute_one(reader, GROUP, result.session).frame
        assert alone is not None and result.frame is not None
        pd.testing.assert_frame_equal(result.frame, alone)
