"""The forward-outcome arithmetic on a hand-built panel with known answers: return, excess over
the benchmark, favourable and adverse excursion from the highs and lows, realised volatility, a
DELISTED name measured to its last bar, a gap at the end (a reason, no row), and names not
eligible at S (no bar at S, or not in the universe) left out without a reason."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from algotrade.core.time.calendar import sessions_ending
from algotrade_ingestion.tasks.derived.outcome_paths import (
    NO_END_BAR,
    TRADING_DAYS,
    Window,
    window_rows,
)

T = date(2026, 10, 2)
WINDOW = Window(tuple(sessions_ending(T, 5)))  # h = 4
SPY = "EQ:SPY"


def _bars(closes: dict[str, list[float | None]], highs: dict[str, list[float]] | None = None,
          lows: dict[str, list[float]] | None = None) -> pd.DataFrame:  # fmt: skip
    rows = []
    for iid, series in closes.items():
        for i, (day, close) in enumerate(zip(WINDOW.sessions, series, strict=True)):
            if close is None:
                continue
            high = (highs or {}).get(iid, [c or 0 for c in series])[i]
            low = (lows or {}).get(iid, [c or 0 for c in series])[i]
            rows.append({"instrument_id": iid, "session_date": day, "close": close,
                         "high": high, "low": low})  # fmt: skip
    return pd.DataFrame(rows)


def _by_id(rows: pd.DataFrame) -> dict[str, dict[str, object]]:
    return {str(r["instrument_id"]): dict(r) for _, r in rows.iterrows()}


def test_complete_window_measures_return_excess_and_path() -> None:
    bars = _bars(
        {"EQ:A": [100, 104, 96, 102, 110], SPY: [400, 404, 400, 408, 420]},
        highs={"EQ:A": [101, 106, 98, 103, 112]},
        lows={"EQ:A": [99, 101, 90, 100, 108]},
    )
    rows, reasons = window_rows(bars, WINDOW, {"EQ:A", SPY}, SPY, {})
    a = _by_id(rows)["EQ:A"]
    assert reasons == {}
    assert a["fwd_return"] == pytest.approx(0.10)
    assert a["fwd_excess_return"] == pytest.approx(0.10 - 0.05)
    assert a["fwd_max_return"] == pytest.approx(0.12)  # high 112 after S
    assert a["fwd_max_drawdown"] == pytest.approx(0.10)  # low 90 after S
    logs = np.diff(np.log([100, 104, 96, 102, 110]))
    assert a["fwd_realised_vol"] == pytest.approx(np.std(logs, ddof=1) * np.sqrt(TRADING_DAYS))
    assert a["outcome_status"] == "COMPLETE"


def test_s_high_and_low_are_not_part_of_the_path() -> None:
    bars = _bars({"EQ:A": [100, 101, 102, 103, 104]}, highs={"EQ:A": [150, 101, 102, 103, 104]},
                 lows={"EQ:A": [50, 101, 102, 103, 104]})  # fmt: skip
    a = _by_id(window_rows(bars, WINDOW, {"EQ:A"}, None, {})[0])["EQ:A"]
    assert a["fwd_max_return"] == pytest.approx(0.04)
    assert a["fwd_max_drawdown"] == 0.0  # no low below close(S): floored at 0
    assert np.isnan(a["fwd_excess_return"])  # no benchmark


def test_delisted_name_is_measured_to_its_last_bar() -> None:
    bars = _bars({"EQ:D": [50, 45, 40, None, None], SPY: [400, 404, 400, 408, 420]})
    rows, reasons = window_rows(bars, WINDOW, {"EQ:D", SPY}, SPY, {"EQ:D": WINDOW.sessions[3]})
    d = _by_id(rows)["EQ:D"]
    assert d["outcome_status"] == "DELISTED"
    assert d["fwd_return"] == pytest.approx(-0.20)
    assert d["fwd_excess_return"] == pytest.approx(-0.20 - 0.0)  # SPY 400 -> 400 to that bar
    assert d["fwd_max_drawdown"] == pytest.approx(0.20)
    assert reasons == {}


def test_a_delisting_noticed_after_t_still_counts() -> None:
    bars = _bars({"EQ:D": [50, 45, None, None, None]})
    noticed = {"EQ:D": date(2026, 10, 9)}  # the weekly reference build, a week after T
    d = _by_id(window_rows(bars, WINDOW, {"EQ:D"}, None, noticed)[0])["EQ:D"]
    assert d["outcome_status"] == "DELISTED" and d["fwd_return"] == pytest.approx(-0.10)


def test_delisted_the_day_after_s_has_a_flat_path() -> None:
    bars = _bars({"EQ:D": [50, None, None, None, None]})
    d = _by_id(window_rows(bars, WINDOW, {"EQ:D"}, None, {"EQ:D": WINDOW.sessions[1]})[0])["EQ:D"]
    assert (d["fwd_return"], d["fwd_max_return"], d["fwd_max_drawdown"]) == (0.0, 0.0, 0.0)
    assert np.isnan(d["fwd_realised_vol"])  # under two returns


def test_a_gap_at_the_end_is_a_reason_not_a_row() -> None:
    bars = _bars({"EQ:G": [10, 11, 12, 13, None], "EQ:L": [10, 11, None, None, None]})
    stale = {"EQ:L": WINDOW.start}  # a delisting recorded on or before S is not this window's
    rows, reasons = window_rows(bars, WINDOW, {"EQ:G", "EQ:L"}, None, stale)
    assert rows.empty
    assert reasons == {"EQ:G": NO_END_BAR, "EQ:L": NO_END_BAR}


def test_only_universe_names_with_a_bar_at_s_are_eligible() -> None:
    bars = _bars({"EQ:A": [10, 11, 12, 13, 14], "EQ:N": [None, 11, 12, 13, 14],
                  "EQ:X": [10, 11, 12, 13, 14]})  # fmt: skip
    rows, reasons = window_rows(bars, WINDOW, {"EQ:A", "EQ:N"}, None, {})
    assert list(rows["instrument_id"]) == ["EQ:A"]
    assert reasons == {}


def test_a_gap_inside_the_window_is_skipped_by_the_returns() -> None:
    bars = _bars({"EQ:A": [100, None, 121, 121, 133.1]})
    a = _by_id(window_rows(bars, WINDOW, {"EQ:A"}, None, {})[0])["EQ:A"]
    logs = np.log([121 / 100, 1.0, 1.1])  # the return over the gap is one return
    assert a["fwd_realised_vol"] == pytest.approx(np.std(logs, ddof=1) * np.sqrt(TRADING_DAYS))


def test_no_eligible_name_gives_no_rows() -> None:
    rows, reasons = window_rows(_bars({"EQ:A": [None, 1, 1, 1, 1]}), WINDOW, {"EQ:A"}, None, {})
    assert rows.empty and reasons == {}
    assert WINDOW.horizon == 4 and WINDOW.start < WINDOW.end == T
