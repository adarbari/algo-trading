"""``earnings@v1``: next / last dates as known on each session (stored snapshots on or before
it), moved dates, report time, and sessions to the report across holidays."""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

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


def _full_reading(stored: pd.DataFrame) -> pd.DataFrame:
    """``valid_events`` as it was before ``since`` (PR #130): the reference it must equal."""
    rows = stored.assign(
        report=pd.to_datetime(stored["ts"], utc=True).dt.date,
        snapshot=pd.to_datetime(stored["session_date"]).dt.date,
    )
    ranges = rows.groupby("snapshot")["report"].agg(["min", "max"])
    snaps = ranges.index.to_numpy()
    ranges["min"] = np.minimum(ranges["min"].to_numpy(), snaps)
    reports = np.array(sorted(rows["report"].unique()))
    covers = (ranges["min"].to_numpy()[None, :] <= reports[:, None]) & (
        reports[:, None] <= ranges["max"].to_numpy()[None, :]
    )
    last = covers.shape[1] - 1 - np.argmax(covers[:, ::-1], axis=1)
    authority = dict(zip(reports, snaps[last], strict=True))
    return rows[rows["snapshot"] == rows["report"].map(authority)]


def random_snapshots(seed: int, n: int = 60) -> pd.DataFrame:
    """``n`` daily snapshots of 8 names: each lists reports up to 20 days ahead, some move or
    vanish, and a few snapshots also carry past dates (a backfill into one partition)."""
    rng = np.random.default_rng(seed)
    start = date(2026, 3, 2)
    rows = []
    for k in range(n):
        snap = start + timedelta(days=int(k * 1.4))
        back = 40 if rng.random() < 0.1 else 0
        for i in range(8):
            for _ in range(int(rng.integers(0, 3))):
                day = snap + timedelta(days=int(rng.integers(-back, 21)))
                rows.append(
                    {
                        "instrument_id": f"EQ:N{i}",
                        "ts": pd.Timestamp(day, tz="UTC")
                        + pd.Timedelta(hours=int(rng.integers(0, 24))),
                        "time": str(rng.choice(["pre_market", "after_hours", "time-not-supplied"])),
                        "session_date": snap,
                    }
                )
    return pd.DataFrame(rows).sort_values("session_date", kind="stable").reset_index(drop=True)


@pytest.mark.parametrize("seed", range(5))
def test_valid_events_equals_the_full_reading_with_and_without_since(seed: int) -> None:
    stored = random_snapshots(seed)
    want = _full_reading(stored)
    pd.testing.assert_frame_equal(earnings.valid_events(stored), want)
    for since in (date(2026, 3, 1), date(2026, 4, 10), date(2026, 5, 20), date(2027, 1, 1)):
        pd.testing.assert_frame_equal(
            earnings.valid_events(stored, since), want[want["report"] >= since]
        )
