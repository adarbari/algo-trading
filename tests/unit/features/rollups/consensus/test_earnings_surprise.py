"""``earnings_surprise@v1``: surprise computed from reported vs forecast, point in time."""

from collections.abc import Sequence
from datetime import date, timedelta

import pandas as pd
import pytest

from algotrade.features.rollups.consensus import earnings_surprise
from algotrade.features.rollups.corporate import earnings
from tests.helpers.stored_frames import stamped

SNAPSHOT = date(2026, 10, 2)
type Row = tuple[str, date, float | None, float | None, date]


def _events(
    rows: Sequence[Row], stored: date = SNAPSHOT, vendor: float | None = None
) -> pd.DataFrame:
    """(instrument, report date, eps_reported, eps_forecast, known_from) rows of one night, each
    with the vendor's own surprise figure ``vendor`` (none: the calendar gave none)."""
    frame: list[dict[str, object]] = [
        {
            "instrument_id": i,
            "ts": pd.Timestamp(d, tz="UTC"),
            "time": "unknown",
            "known_from": known,
            "eps_reported": reported,
            "eps_forecast": forecast,
            "surprise_pct": vendor,
            "reported": reported is not None,
        }
        for i, d, reported, forecast, known in rows
    ]
    return stamped(frame, stored, "r")


def _at(stored: pd.DataFrame, session: date) -> pd.DataFrame:
    out = earnings_surprise.compute({earnings.EVENTS: stored}, session, None)
    return out.set_index("instrument_id")


def _quarters(i: str, results: Sequence[tuple[float, float]]) -> list[Row]:
    """Quarterly reports (80 days apart), oldest first, each known from its own day."""
    days = [date(2025, 7, 1) + timedelta(days=80 * n) for n in range(len(results))]
    return [(i, d, r, f, d) for d, (r, f) in zip(days, results, strict=True)]


def test_a_beat_and_a_miss_are_computed_from_the_two_numbers() -> None:
    beat = _at(_events([("EQ:B", date(2026, 9, 20), 1.10, 1.00, date(2026, 9, 20))]), SNAPSHOT)
    miss = _at(_events([("EQ:M", date(2026, 9, 20), 0.45, 0.50, date(2026, 9, 20))]), SNAPSHOT)
    assert beat.loc["EQ:B", "last_surprise_pct"] == pytest.approx(10.0)
    assert miss.loc["EQ:M", "last_surprise_pct"] == pytest.approx(-10.0)
    assert beat.loc["EQ:B", "surprise_status"] == "OK"
    assert (beat.loc["EQ:B", "beats_4q"], miss.loc["EQ:M", "beats_4q"]) == (1, 0)
    assert beat.loc["EQ:B", "last_eps_reported"] == pytest.approx(1.10)
    assert beat.loc["EQ:B", "last_report_date"] == date(2026, 9, 20)


def test_the_surprise_divides_by_the_absolute_forecast() -> None:
    # A loss smaller than forecast is a beat: -0.20 against -0.40 is +50%, not -50%.
    got = _at(_events([("EQ:A", date(2026, 9, 20), -0.20, -0.40, date(2026, 9, 20))]), SNAPSHOT)
    assert got.loc["EQ:A", "last_surprise_pct"] == pytest.approx(50.0)
    assert got.loc["EQ:A", "beats_4q"] == 1


def test_a_missing_forecast_gives_no_surprise_and_the_status_says_so() -> None:
    got = _at(_events([("EQ:N", date(2026, 9, 20), 0.30, None, date(2026, 9, 20))]), SNAPSHOT)
    assert got.loc["EQ:N", "surprise_status"] == "NO_FORECAST"
    assert got.loc["EQ:N", ["last_surprise_pct", "last_surprise_eps", "beats_4q"]].isna().all()
    assert got.loc["EQ:N", "reports_4q"] == 0
    assert got.loc["EQ:N", "last_eps_reported"] == pytest.approx(0.30)


def test_the_floor_drops_the_percent_but_keeps_the_beat_and_the_dollar_surprise() -> None:
    rows = [
        ("EQ:Z", date(2026, 9, 20), 0.30, 0.0, date(2026, 9, 20)),  # a zero forecast
        ("EQ:S", date(2026, 9, 20), 0.10, 0.04, date(2026, 9, 20)),  # below five cents
        ("EQ:E", date(2026, 9, 20), 0.15, 0.05, date(2026, 9, 20)),  # at the floor: kept
    ]
    got = _at(_events(rows), SNAPSHOT)
    for iid in ("EQ:Z", "EQ:S"):
        assert pd.isna(got.loc[iid, "last_surprise_pct"])
        assert got.loc[iid, "surprise_status"] == "OK"
        assert (got.loc[iid, "reports_4q"], got.loc[iid, "beats_4q"]) == (1, 1)
        assert pd.isna(got.loc[iid, "surprise_median_4q"])
    assert got.loc["EQ:Z", "last_surprise_eps"] == pytest.approx(0.30)
    assert got.loc["EQ:S", "last_surprise_eps"] == pytest.approx(0.06)
    assert got.loc["EQ:E", "last_surprise_pct"] == pytest.approx(200.0)


def test_a_report_not_known_by_the_session_is_ignored() -> None:
    old = ("EQ:A", date(2026, 6, 20), 1.0, 1.0, date(2026, 6, 20))
    fresh = ("EQ:A", date(2026, 9, 20), 2.0, 1.0, date(2026, 10, 9))  # known a week late
    stored = _events([old, fresh], stored=date(2026, 10, 9))
    before = _at(stored, date(2026, 10, 5))
    assert before.loc["EQ:A", "last_report_date"] == date(2026, 6, 20)
    assert before.loc["EQ:A", "last_surprise_pct"] == pytest.approx(0.0)
    assert before.loc["EQ:A", "beats_4q"] == 0  # meeting the forecast is not a beat
    after = _at(stored, date(2026, 10, 9))
    assert after.loc["EQ:A", "last_report_date"] == date(2026, 9, 20)
    assert after.loc["EQ:A", "last_surprise_pct"] == pytest.approx(100.0)


def test_the_four_report_columns_cover_the_last_four_reports() -> None:
    results = [(9.0, 1.0), (1.2, 1.0), (0.8, 1.0), (1.0, 1.0), (1.1, 1.0)]  # oldest first
    got = _at(_events(_quarters("EQ:A", results)), SNAPSHOT)
    row = got.loc["EQ:A"]
    # The oldest (a +800% beat) is outside the last four: +20, -20, 0, +10 -> median 5, 2 beats.
    assert (row["reports_4q"], row["beats_4q"]) == (4, 2)
    assert row["surprise_median_4q"] == pytest.approx(5.0)
    assert row["last_surprise_pct"] == pytest.approx(10.0)


def test_a_name_that_has_not_reported_has_a_row_with_no_report() -> None:
    got = _at(_events([("EQ:F", date(2026, 10, 20), None, 1.0, SNAPSHOT)]), SNAPSHOT)
    assert got.loc["EQ:F", "surprise_status"] == "NO_REPORT"
    assert got["last_surprise_pct"].isna().all() and got["reports_4q"].isna().all()


def test_the_vendors_figure_is_a_check_never_the_value() -> None:
    row = ("EQ:A", date(2026, 9, 20), 1.10, 1.00, date(2026, 9, 20))
    for vendor in (None, 999.0, 10.0):  # absent, nonsense, agreeing: our value stands
        got = _at(_events([row], vendor=vendor), SNAPSHOT)
        assert got.loc["EQ:A", "last_surprise_pct"] == pytest.approx(10.0)
        assert got.loc["EQ:A", "surprise_status"] == "OK"


def test_one_placeholder_result_does_not_move_the_median() -> None:
    results = [(1.10, 1.0), (1.20, 1.0), (1.05, 1.0), (999.0, 1.0)]  # +10, +20, +5, +99800
    got = _at(_events(_quarters("EQ:A", results)), SNAPSHOT)
    assert got.loc["EQ:A", "surprise_median_4q"] == pytest.approx(15.0)  # the mean is 24,959
    assert got.loc["EQ:A", "beats_4q"] == 4


def test_a_sign_conflict_is_null_and_left_out_of_the_four_reports() -> None:
    # Reported -0.67 against a listed forecast of 1.00; the vendor's +33 is the surprise against
    # -1.00: the calendar lost the forecast's minus sign. The forecast is not flipped.
    day = date(2026, 9, 20)
    earlier = _events(_quarters("EQ:C", [(1.10, 1.0), (1.20, 1.0)]))
    conflict = _events([("EQ:C", day, -0.67, 1.00, day)], vendor=33.0)
    stored = pd.concat([earlier, conflict], ignore_index=True)
    row = _at(stored, SNAPSHOT).loc["EQ:C"]
    assert row["surprise_status"] == "SIGN_CONFLICT"
    assert row[["last_surprise_pct", "last_surprise_eps"]].isna().all()
    assert row["last_eps_forecast"] == pytest.approx(1.00)  # as stored, never flipped
    assert (row["reports_4q"], row["beats_4q"]) == (2, 2)  # the two earlier reports only
    assert row["surprise_median_4q"] == pytest.approx(15.0)
    # Without the vendor's witness the report keeps our value: -167%, a miss.
    kept = _at(_events([("EQ:C", day, -0.67, 1.00, day)]), SNAPSHOT).loc["EQ:C"]
    assert kept["surprise_status"] == "OK" and kept["last_surprise_pct"] == pytest.approx(-167.0)
    # A vendor figure that differs from ours but not by the sign (another basis) is no conflict.
    other = _at(_events([("EQ:C", day, 1.50, 1.48, day)], vendor=-29.0), SNAPSHOT).loc["EQ:C"]
    assert other["surprise_status"] == "OK" and other["last_surprise_pct"] == pytest.approx(
        1.35, abs=0.01
    )


def test_a_snapshot_stored_after_the_session_does_not_move_it() -> None:
    # The report is in a night stored on 10-12 but known from 10-05; at 10-03 it is unknown.
    first = _events([("EQ:A", date(2026, 6, 20), 1.0, 1.0, date(2026, 6, 20))])
    later = _events([("EQ:A", date(2026, 10, 5), 3.0, 1.0, date(2026, 10, 5))], date(2026, 10, 12))
    stored = pd.concat([first, later], ignore_index=True)
    assert _at(stored, date(2026, 10, 3)).loc["EQ:A", "last_report_date"] == date(2026, 6, 20)
    assert _at(stored, date(2026, 10, 6)).loc["EQ:A", "last_report_date"] == date(2026, 10, 5)
    only_first = _at(first, date(2026, 10, 3))
    pd.testing.assert_frame_equal(_at(stored, date(2026, 10, 3)), only_first)
