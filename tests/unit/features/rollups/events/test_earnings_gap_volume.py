"""``earnings_gap_volume@v1``: the last report's window volume over the 20 sessions before it,
the same report as ``earnings_reaction@v1`` counts, null (never zero) when a bar is missing."""

from datetime import date

import pandas as pd
import pytest

from algotrade.core.time.calendar import next_session, previous_session, sessions_ending
from algotrade.features.rollups.corporate import earnings
from algotrade.features.rollups.corporate.earnings_reaction import LOOKBACK
from algotrade.features.rollups.events import earnings_gap_volume as gv
from tests.helpers.stored_frames import stamped

SESSION = date(2026, 10, 2)
A, SPY = "EQ:A", "EQ:SPY"
SYMBOLS = pd.DataFrame({"instrument_id": [A, SPY], "symbol": ["A", "SPY"]})


def _events(rows: list[tuple[str, date]]) -> pd.DataFrame:
    frame = [
        {"instrument_id": i, "ts": pd.Timestamp(d, tz="UTC"), "time": "unknown",
         "known_from": d, "reported": True}
        for i, d in rows
    ]  # fmt: skip
    return stamped(frame, SESSION, "r")


def _bars(
    volume: dict[date, float] | None = None,
    missing: set[tuple[str, date]] = frozenset(),  # type: ignore[assignment]
) -> pd.DataFrame:
    rows = []
    for day in sessions_ending(SESSION, LOOKBACK + 1):
        for iid in (A, SPY):
            if (iid, day) in missing:
                continue
            vol = (volume or {}).get(day, 1000.0) if iid == A else 1000.0
            rows.append(
                {"instrument_id": iid, "session_date": day, "open": 100.0, "high": 100.0,
                 "low": 100.0, "close": 100.0, "volume": vol}
            )  # fmt: skip
    return pd.DataFrame(rows)


def _ratio(reports: list[tuple[str, date]], bars: pd.DataFrame) -> float:
    inputs = {earnings.EVENTS: _events(reports), "bars/1d": bars, "instruments/symbol_ids": SYMBOLS}
    out = gv.compute(inputs, SESSION, None).set_index("instrument_id")
    return float(out.at[A, "reaction_volume_ratio"])


def test_the_ratio_is_the_last_reports_window_over_its_pre_event_base() -> None:
    e = date(2026, 9, 16)
    heavy = {previous_session(e): 3000.0, e: 3000.0, next_session(e): 3000.0}
    # the window's mean is 3000; the base is (19 x 1000 + 3000) / 20 = 1100
    assert _ratio([(A, e)], _bars(volume=heavy)) == pytest.approx(3000 / 1100)


def test_an_older_report_does_not_set_the_ratio() -> None:
    old, last = date(2026, 6, 10), date(2026, 9, 16)
    spike = {previous_session(old): 9000.0, old: 9000.0, next_session(old): 9000.0}
    assert _ratio([(A, old), (A, last)], _bars(volume=spike)) == pytest.approx(1.0)


def test_no_counted_report_or_a_missing_bar_is_null_never_zero() -> None:
    e = date(2026, 9, 16)
    assert pd.isna(_ratio([("EQ:OTHER", e)], _bars()))  # A has no report
    open_window = date(2026, 10, 2)  # E+1 is after the session: not counted yet
    assert pd.isna(_ratio([(A, open_window)], _bars()))
    assert pd.isna(_ratio([(A, e)], _bars(missing={(A, next_session(e))})))


def test_rows_are_dense_over_the_session_s_traded_instruments() -> None:
    inputs = {earnings.EVENTS: _events([(A, date(2026, 9, 16))]), "bars/1d": _bars(),
              "instruments/symbol_ids": SYMBOLS}  # fmt: skip
    out = gv.compute(inputs, SESSION, None)
    assert set(out["instrument_id"]) == {A, SPY}
