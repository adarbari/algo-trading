"""``earnings_reaction@v1``: the E-1 to E+1 excess return, point in time (ED4b)."""

from datetime import date

import pandas as pd
import pytest

from algotrade.core.time.calendar import next_session, previous_session, sessions_ending
from algotrade.features.rollups.corporate import earnings, earnings_reaction
from algotrade.features.rollups.corporate.earnings_reaction import LOOKBACK
from tests.helpers.stored_frames import stamped

STORED = date(2026, 10, 2)  # the backfill's own session: every past report is a history row
SESSION = date(2026, 10, 2)
A, SPY = "EQ:A", "EQ:SPY"
SYMBOLS = pd.DataFrame({"instrument_id": [A, SPY], "symbol": ["A", "SPY"]})


def _events(rows: list[tuple[str, date, date]]) -> pd.DataFrame:
    """(instrument, report date, known_from) rows, all stored on ``STORED``."""
    frame = [
        {
            "instrument_id": i,
            "ts": pd.Timestamp(d, tz="UTC"),
            "time": "unknown",
            "known_from": k,
            "reported": k < STORED,
        }
        for i, d, k in rows
    ]
    return stamped(frame, STORED, "r")


def _bars(
    session: date = SESSION,
    close: dict[date, float] | None = None,
    volume: dict[date, float] | None = None,
    spy_close: dict[date, float] | None = None,
    missing: set[tuple[str, date]] = frozenset(),  # type: ignore[assignment]
) -> pd.DataFrame:
    """A 100.0 close and 1000 volume everywhere, but where overridden; ``missing``: no bar."""
    rows = []
    for day in sessions_ending(session, LOOKBACK + 1):
        for iid, over in ((A, close or {}), (SPY, spy_close or {})):
            if (iid, day) in missing:
                continue
            px = over.get(day, 100.0)
            vol = (volume or {}).get(day, 1000.0) if iid == A else 1000.0
            rows.append(
                {"instrument_id": iid, "session_date": day, "open": px, "high": px,
                 "low": px, "close": px, "volume": vol}
            )  # fmt: skip
    return pd.DataFrame(rows)


def _compute(reports: list[tuple[str, date, date]], bars: pd.DataFrame, session: date = SESSION):
    inputs = {earnings.EVENTS: _events(reports), "bars/1d": bars, "instruments/symbol_ids": SYMBOLS}
    return earnings_reaction.compute(inputs, session, None)


def _row(frame: pd.DataFrame, iid: str = A) -> pd.Series:
    return frame.set_index("instrument_id").loc[iid]


def test_excess_return_over_the_two_session_window_and_sessions_since_across_a_holiday() -> None:
    e = date(2025, 11, 26)  # Wed; Thursday is Thanksgiving: E+1 is Friday 11-28
    before, after = date(2025, 11, 25), date(2025, 11, 28)
    bars = _bars(
        close={before: 100.0, e: 90.0, after: 110.0},
        spy_close={before: 200.0, after: 202.0},  # SPY +1%
    )
    out = _compute([(A, e, e)], bars, date(2025, 12, 2))
    got = _row(out)
    assert got["reaction_excess_return"] == pytest.approx(0.09)  # the 11-26 dip is ignored
    assert got["reaction_end_date"] == after
    assert got["sessions_since_reaction"] == 2  # Dec 1, Dec 2: the holiday is no session
    assert _row(_compute([(A, e, e)], bars, after))["sessions_since_reaction"] == 0


def test_pre_event_adv_excludes_the_event_volume() -> None:
    e = date(2026, 9, 16)  # Wed: E-1 is 09-15
    bars = _bars(volume={date(2026, 9, 16): 9000.0, date(2026, 9, 17): 5000.0})
    got = _row(_compute([(A, e, e)], bars))
    assert got["pre_event_adv_usd_20d"] == 100.0 * 1000.0  # mean of 20 sessions to E-1


def test_open_window_report_does_not_count_yet() -> None:
    e = date(2026, 10, 2)  # reports today: E+1 is after the session
    assert _compute([(A, e, e)], _bars()).empty


def test_null_when_the_spy_bar_is_missing_never_zero() -> None:
    e = date(2026, 9, 16)
    bars = _bars(close={date(2026, 9, 17): 110.0}, missing={(SPY, date(2026, 9, 17))})
    got = _row(_compute([(A, e, e)], bars))
    assert pd.isna(got["reaction_excess_return"])
    assert got["reaction_end_date"] == date(2026, 9, 17)  # the dates stay known


def test_null_when_the_instrument_bar_is_missing() -> None:
    e = date(2026, 9, 16)
    bars = _bars(missing={(A, date(2026, 9, 15))})
    assert pd.isna(_row(_compute([(A, e, e)], bars))["reaction_excess_return"])


QUARTERS = [date(2025, 10, 15), date(2026, 1, 21), date(2026, 4, 22), date(2026, 7, 22)]


def test_volume_ratio_is_the_mean_of_four_reports_and_null_below_four() -> None:
    # each window's three sessions trade 3000; its 20-session pre-event mean (ending at E-1,
    # itself heavy) is (19 x 1000 + 3000) / 20 = 1100: 3000 / 1100 for every report
    heavy = {}
    for q in QUARTERS:
        for d in (previous_session(q), q, next_session(q)):
            heavy[d] = 3000.0
    bars = _bars(volume=heavy)
    reports = [(A, q, q) for q in QUARTERS]
    got = _row(_compute(reports, bars))
    assert got["earnings_volume_ratio"] == pytest.approx(3000 / 1100)
    assert pd.isna(_row(_compute(reports[1:], bars))["earnings_volume_ratio"])  # three reports
    assert not pd.isna(_row(_compute(reports[1:], bars))["reaction_excess_return"])


def test_truncation_invariance() -> None:
    """The value at S is unchanged when bars after S and reports known after S are deleted."""
    reports = [(A, q, q) for q in QUARTERS]
    full = _bars(date(2026, 10, 16), close={date(2026, 10, 9): 150.0})  # a later spike
    later = [*reports, (A, date(2026, 10, 7), date(2026, 10, 5))]  # known after S
    kept = full[full["session_date"] <= SESSION]
    expected = _compute(reports, kept)
    got = _compute(later, kept)
    pd.testing.assert_frame_equal(expected, got)
    # the reaction of the later report is not read: window not closed by S, not known by S
    assert _row(got)["reaction_end_date"] == date(2026, 7, 23)


def test_deterministic() -> None:
    reports = [(A, q, q) for q in QUARTERS]
    bars = _bars(close={date(2026, 7, 23): 105.0})
    pd.testing.assert_frame_equal(_compute(reports, bars), _compute(reports, bars))
