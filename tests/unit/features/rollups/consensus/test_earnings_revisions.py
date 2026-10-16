"""``earnings_revisions@v1``: the forecast of the next report across the nightly snapshots."""

from datetime import date

import pandas as pd
import pytest

from algotrade.features.rollups.consensus import earnings_revisions
from algotrade.features.rollups.corporate import earnings
from tests.helpers.stored_frames import stamped

REPORT = date(2026, 11, 10)
SEP, DEC = "Sep/2026", "Dec/2026"


def _night(
    night: date,
    rows: list[tuple[str, float | None, float | None]],
    *,
    quarter: str | None = SEP,
    report: date = REPORT,
    carried_from: date | None = None,
) -> pd.DataFrame:
    """One nightly snapshot: (instrument, forecast, estimates) of one report each; a row
    ``carried_from`` a night is a copy over a failed fetch."""
    frame: list[dict[str, object]] = [
        {
            "instrument_id": i,
            "ts": pd.Timestamp(report, tz="UTC"),
            "time": "unknown",
            "known_from": night,
            "fiscal_quarter": quarter,
            "eps_forecast": forecast,
            "estimates": estimates,
            "eps_reported": None,
            "reported": False,
            "carried_from": carried_from,
        }
        for i, forecast, estimates in rows
    ]
    return stamped(frame, night, f"r{night}")


def _at(nights: list[pd.DataFrame], session: date) -> pd.DataFrame:
    stored = pd.concat(nights, ignore_index=True)
    return earnings_revisions.compute({earnings.EVENTS: stored}, session, None).set_index(
        "instrument_id"
    )


def _row(nights: list[pd.DataFrame], session: date, iid: str = "EQ:A") -> pd.Series:
    row = _at(nights, session).loc[iid]
    assert isinstance(row, pd.Series)
    return row


A = "EQ:A"
HISTORY = [
    _night(date(2026, 10, 2), [(A, 1.00, 10)]),
    _night(date(2026, 10, 9), [(A, 1.10, 12)]),
    _night(date(2026, 10, 16), [(A, 0.88, 12)]),
]


def test_the_revision_is_the_percent_change_of_the_same_quarters_forecast() -> None:
    row = _row(HISTORY, date(2026, 10, 16))
    assert row["revision_status"] == "OK"
    assert row["next_eps_forecast"] == pytest.approx(0.88)
    assert row["forecast_revision_7d"] == pytest.approx(-20.0)  # 1.10 -> 0.88
    assert row["estimate_count"] == 12


def test_the_30_day_revision_and_estimate_count_change() -> None:
    nights = [*HISTORY, _night(date(2026, 11, 1), [(A, 1.20, 15)])]
    row = _row(nights, date(2026, 11, 1))  # 30 days back is 10-02
    assert row["forecast_revision_30d"] == pytest.approx(20.0)
    assert row["estimate_count_change_30d"] == 5
    # No night is stored around 10-25 (the 7-day target): that comparison is not made up.
    assert pd.isna(row["forecast_revision_7d"]) and row["revision_status"] == "BUILDING"


def test_history_shorter_than_the_window_is_building_and_null() -> None:
    row = _row(HISTORY, date(2026, 10, 9))  # 7 days back is 10-02: there; 30 days: not
    assert row["forecast_revision_7d"] == pytest.approx(10.0)
    assert pd.isna(row["forecast_revision_30d"]) and pd.isna(row["estimate_count_change_30d"])
    early = _row(HISTORY, date(2026, 10, 5))  # nothing stored on or before 09-28
    assert early["revision_status"] == "BUILDING"
    first = _row(HISTORY[:1], date(2026, 10, 2))
    assert first["revision_status"] == "BUILDING" and pd.isna(first["forecast_revision_7d"])


def test_a_quarter_roll_gives_no_revision() -> None:
    # The snapshot a week back holds the September quarter; the next report is December's.
    nights = [
        _night(date(2026, 10, 9), [(A, 1.00, 10), ("EQ:B", 2.0, 5)], report=date(2026, 10, 12)),
        _night(
            date(2026, 10, 16),
            [(A, 0.50, 8)],
            quarter=DEC,
            report=date(2027, 1, 20),
        ),
        _night(date(2026, 10, 16), [("EQ:B", 2.2, 5)], report=date(2026, 10, 20)),
    ]
    row = _row(nights, date(2026, 10, 16))
    assert row["next_eps_forecast"] == pytest.approx(0.50)
    assert pd.isna(row["forecast_revision_7d"])
    assert row["revision_status"] == "NO_PRIOR"


def test_a_carried_forward_row_is_not_an_observation() -> None:
    nights = [
        _night(date(2026, 10, 8), [(A, 1.00, 10), ("EQ:B", 3.0, 4)]),
        # 10-09's fetch of A's day failed: its row is a copy (carried), with a stale, wrong value
        _night(date(2026, 10, 9), [(A, 9.99, 10)], carried_from=date(2026, 10, 8)),
        _night(date(2026, 10, 9), [("EQ:B", 3.0, 4)], report=date(2026, 11, 11)),
        _night(date(2026, 10, 16), [(A, 1.25, 10), ("EQ:B", 3.0, 4)]),
    ]
    row = _row(nights, date(2026, 10, 16))
    assert row["forecast_revision_7d"] == pytest.approx(25.0)  # against 10-08's real 1.00


def test_a_night_only_carried_is_no_snapshot() -> None:
    nights = [
        _night(date(2026, 10, 2), [(A, 1.00, 10)]),
        _night(date(2026, 10, 9), [(A, 1.00, 10)], carried_from=date(2026, 10, 2)),
        _night(date(2026, 10, 16), [(A, 1.30, 10)]),
    ]
    row = _row(nights, date(2026, 10, 16))
    assert row["revision_status"] == "BUILDING" and pd.isna(row["forecast_revision_7d"])


def test_a_zero_or_tiny_old_forecast_gives_no_percent_change() -> None:
    for old in (0.0, 0.005, 0.04, None):
        nights = [
            _night(date(2026, 10, 9), [(A, old, 10)]),
            _night(date(2026, 10, 16), [(A, 0.40, 10)]),
        ]
        row = _row(nights, date(2026, 10, 16))
        assert pd.isna(row["forecast_revision_7d"])
        assert row["next_eps_forecast"] == pytest.approx(0.40)


def test_a_sign_flip_between_nights_reads_as_about_minus_200_percent() -> None:
    nights = [
        _night(date(2026, 10, 9), [(A, 1.00, 10)]),
        _night(date(2026, 10, 16), [(A, -1.00, 10)]),
    ]
    assert _row(nights, date(2026, 10, 16))["forecast_revision_7d"] == pytest.approx(-200.0)


def test_a_negative_forecast_rising_is_a_positive_revision() -> None:
    nights = [
        _night(date(2026, 10, 9), [(A, -0.50, 10)]),
        _night(date(2026, 10, 16), [(A, -0.25, 10)]),
    ]
    assert _row(nights, date(2026, 10, 16))["forecast_revision_7d"] == pytest.approx(50.0)


def test_a_missing_forecast_and_no_next_report_have_their_status() -> None:
    past = _night(date(2026, 10, 16), [("EQ:P", 1.0, 1)], report=date(2026, 9, 1))
    nights = [_night(date(2026, 10, 16), [(A, None, 3)]), past]
    got = _at(nights, date(2026, 10, 16))
    assert got.loc[A, "revision_status"] == "NO_FORECAST"
    assert pd.isna(got.loc[A, "next_eps_forecast"]) and got.loc[A, "estimate_count"] == 3
    assert got.loc["EQ:P", "revision_status"] == "NO_NEXT"


def test_the_row_order_of_the_snapshots_does_not_matter() -> None:
    nights = [*HISTORY, _night(date(2026, 11, 1), [(A, 1.20, 15)])]
    forward = pd.concat(nights, ignore_index=True)
    shuffled = forward.sample(frac=1.0, random_state=7).reset_index(drop=True)
    for stored in (forward, shuffled):
        got = earnings_revisions.compute({earnings.EVENTS: stored}, date(2026, 11, 1), None)
        assert got.loc[0, "forecast_revision_30d"] == pytest.approx(20.0)
    a = earnings_revisions.compute({earnings.EVENTS: forward}, date(2026, 10, 16), None)
    b = earnings_revisions.compute({earnings.EVENTS: shuffled}, date(2026, 10, 16), None)
    pd.testing.assert_frame_equal(a, b)


def test_a_snapshot_stored_after_the_session_does_not_move_it() -> None:
    later = _night(date(2026, 10, 23), [(A, 5.00, 40)])  # a different forecast, stored a week on
    with_later = pd.concat([*HISTORY, later], ignore_index=True)
    without = pd.concat(HISTORY, ignore_index=True)
    session = date(2026, 10, 16)
    a = earnings_revisions.compute({earnings.EVENTS: with_later}, session, None)
    b = earnings_revisions.compute({earnings.EVENTS: without}, session, None)
    pd.testing.assert_frame_equal(a, b)
    # And the same night's value seen from the later session does move.
    assert _row([*HISTORY, later], date(2026, 10, 23))["next_eps_forecast"] == pytest.approx(5.0)


def test_a_snapshot_further_back_than_the_slack_is_not_used() -> None:
    nights = [
        _night(date(2026, 10, 2), [(A, 1.00, 10)]),
        _night(date(2026, 10, 16), [(A, 1.50, 10)]),
    ]  # 10-09 is the target, 10-02 is a week before it
    row = _row(nights, date(2026, 10, 16))
    assert pd.isna(row["forecast_revision_7d"]) and row["revision_status"] == "BUILDING"
