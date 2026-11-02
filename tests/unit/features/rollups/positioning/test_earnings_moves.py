"""``earnings_moves@v1``: the signed moves of the last twelve closed reports and the stored
implied moves set against them (null, never zero, until a straddle was stored before a report)."""

from datetime import date

import pandas as pd
import pytest

from algotrade.core.time.calendar import next_session, previous_session, sessions_ending
from algotrade.features.rollups.corporate import earnings
from algotrade.features.rollups.positioning import earnings_moves as em
from tests.helpers.stored_frames import stamped

SESSION = date(2026, 10, 2)
A, SPY = "EQ:A", "EQ:SPY"
SYMBOLS = pd.DataFrame({"instrument_id": [A, SPY], "symbol": ["A", "SPY"]})


def _events(days: list[date]) -> pd.DataFrame:
    rows = [
        {"instrument_id": A, "ts": pd.Timestamp(d, tz="UTC"), "time": "unknown",
         "known_from": d, "reported": True}
        for d in days
    ]  # fmt: skip
    return stamped(rows, SESSION, "r")


def _bars(close: dict[date, float]) -> pd.DataFrame:
    rows = []
    for day in sessions_ending(SESSION, em.LOOKBACK + 1):
        for iid in (A, SPY):
            c = close.get(day, 100.0) if iid == A else 100.0
            rows.append({"instrument_id": iid, "session_date": day, "open": c, "high": c,
                         "low": c, "close": c, "volume": 1000.0})  # fmt: skip
    return pd.DataFrame(rows)


def _moved(report: date, after: float) -> dict[date, float]:
    return {next_session(report): after}  # E-1 stays 100


def _straddle(before: date, implied: float, basis: str = "EARNINGS", expiry: date | None = None):
    return {"instrument_id": A, "session_date": before, "implied_move": implied,
            "move_basis": basis, "move_expiry": expiry or date(2026, 12, 1)}  # fmt: skip


def _row(reports: list[date], close: dict[date, float], implied: list[dict] | None = None):
    inputs = {
        earnings.EVENTS: _events(reports),
        "bars/1d": _bars(close),
        "instruments/symbol_ids": SYMBOLS,
        em.IMPLIED: pd.DataFrame(implied) if implied else None,
    }
    return em.compute(inputs, SESSION, None).set_index("instrument_id").loc[A]


R1, R2, R3 = date(2026, 9, 16), date(2026, 6, 10), date(2026, 3, 11)


def test_moves_are_signed_newest_first_with_their_report_dates() -> None:
    close = {**_moved(R1, 110.0), **_moved(R2, 95.0), **_moved(R3, 100.0)}
    row = _row([R1, R2, R3], close)
    assert row["move_1"] == pytest.approx(0.10)
    assert row["move_2"] == pytest.approx(-0.05)
    assert row["move_date_1"] == R1 and row["move_date_2"] == R2 and row["move_date_3"] == R3
    assert row["moves_counted_12"] == 3
    assert row["abs_move_mean_12"] == pytest.approx(0.05)
    assert pd.isna(row["move_4"]) and pd.isna(row["move_date_4"])


def test_a_report_ahead_or_with_an_open_window_is_not_counted() -> None:
    ahead = next_session(SESSION)
    close = _moved(R1, 110.0)
    row = _row([R1, ahead], close)
    assert row["moves_counted_12"] == 1 and row["move_1"] == pytest.approx(0.10)


def test_no_report_is_null_moves_and_a_zero_count() -> None:
    row = _row([SESSION], {})  # a report whose window is still open
    assert row["moves_counted_12"] == 0
    assert pd.isna(row["move_1"]) and pd.isna(row["abs_move_mean_12"])


def test_overpaid_is_null_never_zero_without_a_stored_straddle() -> None:
    row = _row([R1], _moved(R1, 110.0))
    assert pd.isna(row["options_overpaid_n"]) and pd.isna(row["options_overpaid_m"])


def test_overpaid_counts_the_stored_earnings_straddles_above_the_move() -> None:
    close = {**_moved(R1, 110.0), **_moved(R2, 101.0)}
    implied = [
        _straddle(previous_session(R1), 0.06),  # paid 6%, moved 10%: not overpaid
        _straddle(previous_session(R2), 0.05),  # paid 5%, moved 1%: overpaid
    ]
    row = _row([R1, R2, R3], close, implied)
    assert row["options_overpaid_m"] == 2 and row["options_overpaid_n"] == 1


def test_a_term_straddle_or_a_later_partition_does_not_count() -> None:
    close = _moved(R1, 110.0)
    term = _straddle(previous_session(R1), 0.02, basis="TERM")
    later = _straddle(R1, 0.02)  # the session of the report, not the one before it
    short = _straddle(previous_session(R1), 0.02, expiry=date(2026, 9, 1))  # expires before E
    row = _row([R1], close, [term, later, short])
    assert pd.isna(row["options_overpaid_m"])


def test_a_post_close_report_is_not_covered_by_a_straddle_expiring_on_it() -> None:
    close = _moved(R1, 110.0)
    on_report = _straddle(previous_session(R1), 0.02, expiry=R1)
    row = _row([R1], close, [on_report])  # time "unknown": needs an expiry after E
    assert pd.isna(row["options_overpaid_m"])


def test_a_pre_open_report_is_covered_by_a_straddle_expiring_on_it() -> None:
    events = _events([R1])
    events["time"] = "pre_market"
    inputs = {
        earnings.EVENTS: events,
        "bars/1d": _bars(_moved(R1, 110.0)),
        "instruments/symbol_ids": SYMBOLS,
        em.IMPLIED: pd.DataFrame([_straddle(previous_session(R1), 0.02, expiry=R1)]),
    }
    row = em.compute(inputs, SESSION, None).set_index("instrument_id").loc[A]
    assert row["options_overpaid_m"] == 1 and row["options_overpaid_n"] == 0


def test_moves_counted_is_null_without_report_rows_and_zero_with_only_open_ones() -> None:
    only_ahead = _row([SESSION], {})
    assert only_ahead["moves_counted_12"] == 0
    inputs = {
        earnings.EVENTS: _events([R1]).assign(instrument_id="EQ:OTHER"),
        "bars/1d": _bars({}),
        "instruments/symbol_ids": SYMBOLS,
        em.IMPLIED: None,
    }
    out = em.compute(inputs, SESSION, None).set_index("instrument_id")
    assert pd.isna(out.at[A, "moves_counted_12"])
