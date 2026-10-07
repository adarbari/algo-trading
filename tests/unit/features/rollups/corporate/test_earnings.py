"""``earnings@v1``: next / last dates as known on each session (stored snapshots on or before
it), moved dates, report time, and sessions to the report across holidays."""

from collections.abc import Callable
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
    last = date(2027, 1, 1)  # every snapshot stored by then
    pd.testing.assert_frame_equal(earnings.valid_events(stored, last), want)
    for since in (date(2026, 3, 1), date(2026, 4, 10), date(2026, 5, 20), date(2027, 1, 1)):
        pd.testing.assert_frame_equal(
            earnings.valid_events(stored, last, since), want[want["report"] >= since]
        )


def _store_rows(
    writer: object, stored: date, rows: list[tuple[str, date, date]], **extra: object
) -> None:
    """Rows stored on ``stored``: (instrument, report date, known_from); a row known before
    ``stored`` is a reported result."""
    from tests.helpers.stored_frames import stamped  # noqa: PLC0415

    frame = [
        {
            "instrument_id": i,
            "ts": pd.Timestamp(d, tz="UTC"),
            "time": "pre_market",
            "known_from": k,
            "reported": k < stored,
            **extra,
        }
        for i, d, k in rows
    ]
    run = f"r{stored}-{len(rows)}-{len(extra)}"
    writer.write_table("events/earnings", stored, run, stamped(frame, stored, run))  # type: ignore[attr-defined]


MON, TUE, WED, THU = (date(2026, 10, d) for d in (5, 6, 7, 8))


def _monday(with_tuesday: Callable[[object], None] | None) -> dict[str, object]:
    """Monday's earnings@v1 rows by instrument, with Tuesday's partition stored or not."""
    writer, reader = store()
    _store_rows(writer, MON, [("EQ:A", MON, MON), ("EQ:B", WED, MON), ("EQ:D", WED, MON)])
    if with_tuesday is not None:
        with_tuesday(writer)
    frame = compute_one(reader, GROUP, MON).frame
    assert frame is not None
    return frame.set_index("instrument_id").to_dict("index")


def test_a_later_lookback_never_overrules_the_session_s_own_calendar() -> None:
    """Architect review (lookahead): Tuesday's lookback rows for Monday (known on Monday)
    omit A; at session Monday, Tuesday's partition must not become the authority for Monday."""

    def tuesday(writer: object) -> None:
        _store_rows(writer, TUE, [("EQ:C", MON, MON), ("EQ:B", THU, TUE)])

    alone, later = _monday(None), _monday(tuesday)
    for iid in ("EQ:A", "EQ:B", "EQ:D"):
        assert later[iid] == alone[iid], iid
    assert later["EQ:C"]["next_earnings_date"] == MON  # a reported fact known on Monday


def test_a_later_carried_row_never_overrules_the_session_s_own_calendar() -> None:
    """Architect review (lookahead): a forecast Tuesday carried for Thursday is visible at
    Monday through its known_from; it must not make Tuesday the authority for Wednesday."""

    def tuesday(writer: object) -> None:
        _store_rows(
            writer,
            TUE,
            [("EQ:E", THU, date(2026, 10, 2))],
            carried_from=date(2026, 10, 2),
            reported=False,
        )
        _store_rows(writer, TUE, [("EQ:B", THU, TUE)])

    alone, later = _monday(None), _monday(tuesday)
    assert later == alone


def test_a_second_backfill_never_cancels_the_reports_of_the_first() -> None:
    """Regression (architect review of EV1a): a later backfill partition holding only a retried
    day, merged with that night's calendar, spans 09-29..11-06; its range used to make it the
    authority there and drop A's 10-01 report, stored by the first backfill."""
    writer, reader = store()
    first, second = date(2026, 10, 6), date(2026, 10, 7)
    a, b = ("EQ:A", date(2026, 10, 1)), ("EQ:B", date(2026, 9, 30))
    _store_rows(writer, first, [(*a, a[1]), (*b, b[1]), ("EQ:C", date(2026, 10, 20), first)])
    retried = date(2026, 9, 29)  # failed in the first backfill
    _store_rows(writer, second, [("EQ:D", retried, retried), ("EQ:C", date(2026, 11, 6), second)])
    frame = compute_one(reader, GROUP, date(2026, 10, 8)).frame
    assert row(frame, "EQ:A")["last_earnings_date"] == a[1]
    assert row(frame, "EQ:B")["last_earnings_date"] == b[1]
    assert row(frame, "EQ:D")["last_earnings_date"] == retried
    c = row(frame, "EQ:C")  # a forecast moved by the later calendar
    assert c["next_earnings_date"] == date(2026, 11, 6)


def test_a_history_row_is_known_from_its_report_date_in_an_earlier_session() -> None:
    writer, reader = store()
    report = date(2019, 5, 1)
    _store_rows(writer, date(2026, 10, 6), [("EQ:A", report, report)])
    assert compute_one(reader, GROUP, date(2019, 4, 30)).no_input
    frame = compute_one(reader, GROUP, date(2019, 5, 2)).frame
    assert row(frame, "EQ:A")["last_earnings_date"] == report


def test_a_carried_forecast_stays_a_forecast() -> None:
    """A row carried forward (``carried_from``) keeps the kind it had where it was fetched: a
    later calendar that moves the report still cancels it."""
    stored = pd.DataFrame(
        {
            "instrument_id": ["EQ:A", "EQ:A"],
            "ts": [pd.Timestamp(2026, 10, 20, tz="UTC"), pd.Timestamp(2026, 10, 27, tz="UTC")],
            "session_date": [date(2026, 10, 2), date(2026, 10, 5)],
            "known_from": [date(2026, 10, 1), date(2026, 10, 5)],
            "carried_from": [date(2026, 10, 1), None],
        }
    )
    stored = pd.concat(
        [stored, stored.iloc[[1]].assign(ts=pd.Timestamp(2026, 10, 15, tz="UTC"))],
        ignore_index=True,
    )  # the 10-05 calendar covers 10-15..10-27 and does not list 10-20
    valid = earnings.valid_events(stored, date(2026, 10, 5))
    assert sorted(valid["report"]) == [date(2026, 10, 15), date(2026, 10, 27)]


def test_recomputing_a_session_after_later_nights_changes_nothing() -> None:
    """Idempotence (architect review): a session computed with only its own partitions and
    again with later ones stored (lookback rows of the same reports with other fields, a
    carried copy, a moved forecast) gives identical earnings@v1 and earnings_schedule@v1."""
    from algotrade.features.rollups.corporate import earnings_schedule  # noqa: PLC0415

    def own(writer: object) -> None:
        _store_rows(writer, date(2026, 10, 2), [("EQ:C", date(2026, 9, 30), date(2026, 9, 30))])
        _store_rows(writer, MON, [("EQ:A", MON, MON), ("EQ:B", WED, MON), ("EQ:D", THU, MON)])

    def later(writer: object) -> None:
        lookback = [("EQ:A", MON, MON), ("EQ:C", date(2026, 9, 30), date(2026, 9, 30))]
        _store_rows(writer, TUE, lookback, time="after_hours", date_confirmed=True)
        _store_rows(writer, TUE, [("EQ:B", THU, TUE)])  # B moved
        _store_rows(writer, WED, [("EQ:D", THU, MON)], carried_from=MON, reported=False)

    frames = []
    for writes in ((own,), (own, later)):
        writer, reader = store()
        for write in writes:
            write(writer)
        for group in (GROUP, earnings_schedule.GROUP):
            frames.append(compute_one(reader, group, MON).frame)
    for alone, with_later in zip(frames[:2], frames[2:], strict=True):
        assert alone is not None and with_later is not None
        pd.testing.assert_frame_equal(alone, with_later)


def test_an_after_close_8k_reports_on_its_new_york_day_not_the_utc_day() -> None:
    """An Item 2.02 8-K accepted at 20:30 New York time has a ``ts`` on the next UTC day; the
    report day is the writer's ``earnings_date`` (ADR 0050 decision 3), never the UTC date."""
    stored = pd.DataFrame(
        {
            "instrument_id": ["EQ:A", "EQ:B"],
            "ts": [
                pd.Timestamp("2026-10-01T00:30:00Z"),  # 2026-09-30 20:30 New York
                pd.Timestamp("2026-09-30T00:00:00Z"),  # a Nasdaq calendar row: midnight UTC
            ],
            "earnings_date": [date(2026, 9, 30), None],
            "session_date": [date(2026, 10, 1), date(2026, 10, 1)],
            "known_from": [date(2026, 9, 30), date(2026, 10, 1)],
            "reported": [True, False],
        }
    )
    valid = earnings.valid_events(stored, date(2026, 10, 1))
    assert sorted(valid["report"].tolist()) == [date(2026, 9, 30), date(2026, 9, 30)]


def test_the_8k_results_rows_do_not_change_v1() -> None:
    """``earnings@v1`` reads the calendar rows only: the ``sec_8k`` rows (an extra report day, or
    the same day with a different time) wait for the v2 precedence (ADR 0050)."""
    calendar = pd.DataFrame(
        {
            "instrument_id": ["EQ:A"],
            "ts": [pd.Timestamp("2026-09-30T00:00:00Z")],
            "earnings_date": [date(2026, 9, 30)],
            "time": ["pre_market"],
            "session_date": [date(2026, 10, 1)],
            "known_from": [date(2026, 9, 30)],
            "reported": [True],
            "source": ["nasdaq_earnings"],
        }
    )
    eight_k = pd.DataFrame(
        {
            "instrument_id": ["EQ:A", "EQ:A"],
            "ts": [pd.Timestamp("2026-09-30T20:30:00Z"), pd.Timestamp("2026-07-01T20:30:00Z")],
            "earnings_date": [date(2026, 9, 30), date(2026, 7, 1)],
            "time": ["after_hours", "after_hours"],
            "session_date": [date(2026, 10, 1), date(2026, 10, 1)],
            "known_from": [date(2026, 9, 30), date(2026, 7, 1)],
            "reported": [True, True],
            "source": ["sec_8k", "sec_8k"],
        }
    )
    both = pd.concat([calendar, eight_k], ignore_index=True)
    want = earnings.valid_events(calendar, date(2026, 10, 1)).reset_index(drop=True)
    got = earnings.valid_events(both, date(2026, 10, 1)).reset_index(drop=True)
    pd.testing.assert_frame_equal(got, want)
    assert list(got["time"]) == ["pre_market"]
