"""``earnings_reaction@v2``: the E-1 to E+1 excess return, point in time (ED4b)."""

from datetime import date, timedelta

import pandas as pd
import pytest

from algotrade.core.time.calendar import next_session, previous_session, sessions_ending
from algotrade.features.rollups.corporate import earnings, earnings_reaction
from algotrade.features.rollups.corporate.earnings_reaction import MOVES_LOOKBACK
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
    for day in sessions_ending(session, MOVES_LOOKBACK + 1):
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
    got = _row(_compute([(A, e, e)], _bars()))
    assert got["reaction_status"] == "NO_REPORT"  # a window not closed is no report yet
    assert pd.isna(got["reaction_excess_return"]) and pd.isna(got["sessions_since_reaction"])


def test_a_name_with_no_report_gets_a_no_report_row_and_a_missing_bar_is_incomplete() -> None:
    e = date(2026, 9, 16)
    out = _compute([("EQ:OTHER", e, e)], _bars())  # A has no report at all
    assert _row(out)["reaction_status"] == "NO_REPORT"
    assert pd.isna(_row(out)["sessions_since_reaction"])
    assert set(out["instrument_id"]) == {A, SPY}  # dense: every instrument traded on S
    bars = _bars(missing={(A, date(2026, 9, 15))})
    assert _row(_compute([(A, e, e)], bars))["reaction_status"] == "INCOMPLETE"
    assert _row(_compute([(A, e, e)], _bars()))["reaction_status"] == "OK"


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
    got = _compute(later, full)
    pd.testing.assert_frame_equal(expected, got)
    # the reaction of the later report is not read: window not closed by S, not known by S
    assert _row(got)["reaction_end_date"] == date(2026, 7, 23)


def test_deterministic() -> None:
    reports = [(A, q, q) for q in QUARTERS]
    bars = _bars(close={date(2026, 7, 23): 105.0})
    pd.testing.assert_frame_equal(_compute(reports, bars), _compute(reports, bars))


def test_a_missing_pre_event_bar_keeps_the_event_ok_with_a_null_adv() -> None:
    e = date(2026, 9, 16)
    got = _row(_compute([(A, e, e)], _bars(missing={(A, date(2026, 9, 1))})))
    assert got["reaction_status"] == "OK"
    assert not pd.isna(got["reaction_excess_return"]) and pd.isna(got["pre_event_adv_usd_20d"])


def test_a_moved_date_listed_twice_is_one_report() -> None:
    first, moved = date(2026, 7, 22), date(2026, 8, 5)  # one quarter, two dates
    got = _row(_compute([(A, first, first), (A, moved, moved)], _bars()))
    assert got["reaction_end_date"] == date(2026, 7, 23)  # the earliest, not the 08-06 one


class _NoTrading(dict[date, float]):
    """Every session of A traded nothing (a halted or dormant name)."""

    def get(self, key: date, default: float | None = None) -> float:  # type: ignore[override]
        return 0.0


def test_a_name_with_no_pre_event_trading_has_a_null_volume_ratio_never_an_error() -> None:
    """The 2026-10-08 backfill stopped on ``float division by zero`` (a zero pre-event ADV)."""
    reports = [(A, q, q) for q in QUARTERS]
    got = _row(_compute(reports, _bars(volume=_NoTrading({SESSION: 0.0}))))  # non-empty: truthy
    assert pd.isna(got["earnings_volume_ratio"]) and got["pre_event_adv_usd_20d"] == 0.0
    assert got["reaction_status"] == "OK"  # the return does not need volume


PAST = [date(2025, 1, 22), date(2025, 4, 23), date(2025, 7, 23), date(2025, 10, 22)]


def _spikes(moves: dict[date, float]) -> dict[date, float]:
    """Closes giving each report (E) an E-1 to E+1 move of the given share: 100 before, 100 x
    (1 + move) after (a negative move is a fall)."""
    close = {}
    for report, move in moves.items():
        close[next_session(report)] = 100.0 * (1.0 + move)
    return close


def test_past_moves_are_the_absolute_mean_median_and_count_of_closed_reports() -> None:
    moves = {PAST[0]: 0.10, PAST[1]: -0.04, PAST[2]: 0.03, PAST[3]: -0.07}
    got = _row(_compute([(A, q, q) for q in PAST], _bars(close=_spikes(moves))))
    assert got["abs_moves_counted"] == 4
    assert got["abs_move_mean_8"] == pytest.approx(0.06)  # |.10| |-.04| |.03| |-.07|
    assert got["abs_move_median_8"] == pytest.approx(0.055)  # the raw move: SPY is not netted
    assert got["abs_move_mean_4"] == pytest.approx(0.06)  # four reports: the same four
    assert got["abs_move_max_8"] == pytest.approx(0.10)
    assert got["signed_move_mean_8"] == pytest.approx(0.005)  # +.10 -.04 +.03 -.07 over 4
    assert got["up_moves_8"] == 2


def test_past_moves_cover_the_last_eight_reports_only() -> None:
    quarters = [date(2024, 7, 24) + timedelta(days=91 * i) for i in range(9)]
    quarters = [q if q.weekday() < 5 else q + timedelta(days=2) for q in quarters]
    moves = {q: 0.20 if i == 0 else 0.02 for i, q in enumerate(quarters)}  # the oldest is huge
    got = _row(_compute([(A, q, q) for q in quarters], _bars(close=_spikes(moves))))
    assert got["abs_moves_counted"] == 8
    assert got["abs_move_mean_8"] == pytest.approx(0.02)  # the ninth report is not read
    assert got["abs_move_max_8"] == pytest.approx(0.02) and got["up_moves_8"] == 8


def test_a_report_ahead_does_not_hide_the_past_moves() -> None:
    """The name reporting tomorrow is the one an earnings setup needs: its newest report is
    open, but the closed ones before it still give the past moves."""
    ahead = date(2026, 10, 3)
    reports = [(A, q, q) for q in PAST] + [(A, ahead, SESSION)]
    moves = dict.fromkeys(PAST, 0.05)
    got = _row(_compute(reports, _bars(close=_spikes(moves))))
    assert got["abs_moves_counted"] == 4 and got["abs_move_mean_8"] == pytest.approx(0.05)


def test_past_moves_skip_a_report_without_a_bar_and_are_null_never_zero_with_none() -> None:
    moves = {PAST[0]: 0.10, PAST[1]: 0.02}
    bars = _bars(close=_spikes(moves), missing={(A, previous_session(PAST[0]))})
    got = _row(_compute([(A, PAST[0], PAST[0]), (A, PAST[1], PAST[1])], bars))
    assert got["abs_moves_counted"] == 1 and got["abs_move_mean_8"] == pytest.approx(0.02)
    none = _row(_compute([("EQ:OTHER", PAST[0], PAST[0])], _bars()))
    assert none["abs_moves_counted"] == 0
    assert pd.isna(none["abs_move_mean_8"]) and pd.isna(none["abs_move_median_8"])
    assert pd.isna(none["abs_move_mean_4"]) and none["up_moves_8"] == 0


def test_past_moves_use_only_windows_closed_and_known_by_the_session() -> None:
    """The report whose window closes after S, and one known only after S, change nothing."""
    moves = dict.fromkeys(PAST, 0.03)
    session = date(2026, 10, 2)
    full = _bars(date(2026, 10, 16), close={**_spikes(moves), date(2026, 10, 9): 150.0})
    later = [(A, q, q) for q in PAST]
    later += [
        (A, date(2026, 10, 1), date(2026, 10, 1)),  # E+1 is 10-02 = S: closed, counted
        (A, date(2026, 10, 2), date(2026, 10, 2)),  # E+1 after S: open, not counted
        (A, date(2026, 10, 7), date(2026, 10, 5)),
    ]  # known after S: not read
    kept = full[full["session_date"] <= session]
    base = _compute([*later[:5]], kept, session)
    pd.testing.assert_frame_equal(base, _compute(later, full, session))
    assert _row(base)["abs_moves_counted"] == 5  # the four, and the one closing at S


def test_recent_mean_covers_the_newest_four_reports() -> None:
    quarters = [date(2025, 1, 22) + timedelta(days=91 * i) for i in range(6)]
    quarters = [q if q.weekday() < 5 else q + timedelta(days=2) for q in quarters]
    moves = {q: 0.10 if i < 2 else 0.02 for i, q in enumerate(quarters)}  # the old two big
    got = _row(_compute([(A, q, q) for q in quarters], _bars(close=_spikes(moves))))
    assert got["abs_move_mean_4"] == pytest.approx(0.02)
    assert got["abs_move_mean_8"] == pytest.approx((0.20 + 0.08) / 6)
