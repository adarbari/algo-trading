"""``moves``: reaction sessions, multiples, big-move flags, release versions, the macro keys."""

import tomllib
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.rollups.event_study import moves

SESSION = date(2026, 10, 2)
GRID = sessions_ending(SESSION, 60)


def test_macro_keys_match_the_release_calendar_config() -> None:
    config = tomllib.loads(Path("config/site/events/releases.toml").read_text())
    keys = {r["key"] for r in config["release"]}
    assert set(moves.EXPLAINING_KEYS) == keys  # a rollup reads no config: this keeps the list true
    assert tuple(k for k in moves.EXPLAINING_KEYS if k != "FOMC_UNSCHEDULED") == moves.MACRO_KEYS


def test_a_release_at_or_before_the_close_reacts_on_its_own_session_after_it_the_next() -> None:
    day = GRID[-10]
    assert GRID[moves.reaction_position(GRID, day, "08:30")] == day  # type: ignore[index]
    assert GRID[moves.reaction_position(GRID, day, "16:00")] == day  # type: ignore[index]
    assert GRID[moves.reaction_position(GRID, day, "16:30")] == GRID[-9]  # type: ignore[index]


def test_a_closed_day_reacts_on_the_next_session_and_off_grid_days_are_left_out() -> None:
    saturday = date(2026, 9, 26)
    assert GRID[moves.reaction_position(GRID, saturday)] == date(2026, 9, 28)  # type: ignore[index]
    assert moves.reaction_position(GRID, GRID[0]) is None  # no session before it for a prior close
    assert moves.reaction_position(GRID, date(2020, 1, 2)) is None
    # after the session: its reaction is not here yet (R > S is never counted)
    assert moves.reaction_position(GRID, GRID[-1], "17:00") is None
    assert moves.reaction_position(GRID, date(2026, 10, 5)) is None


def test_a_move_is_read_in_normal_days_of_the_session_before() -> None:
    rng = np.random.default_rng(1)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, (60, 1)), axis=0))
    close[40, 0] = close[39, 0] * 1.06
    returns = moves.log_returns(close)
    mult = moves.multiples(returns)
    normal = np.std(returns[20:40, 0], ddof=1)  # the 20 returns ending at the close before
    assert mult[40, 0] == pytest.approx(np.log(1.06) / normal)
    assert np.isnan(mult[:21, 0]).all()  # fewer than 20 returns before: no normal day
    assert moves.big(returns, mult)[40, 0]


def test_a_gap_makes_the_normal_day_null_never_zero() -> None:
    close = 100 + np.arange(60, dtype=float).reshape(-1, 1)
    close[30, 0] = np.nan
    mult = moves.multiples(moves.log_returns(close))
    assert np.isnan(mult[31:51, 0]).all()


def _row(key: str, release: date, known: date, status: str, session: date) -> dict[str, object]:
    return {"release_key": key, "release_date": release, "known_from": known, "status": status,
            "time_et": "08:30", "session_date": session}  # fmt: skip


def test_the_latest_known_version_of_a_release_counts_and_a_moved_date_is_dropped() -> None:
    a, b = date(2026, 9, 10), date(2026, 9, 17)
    rows = pd.DataFrame(
        [
            _row("CPI", a, date(2026, 8, 1), "scheduled", date(2026, 8, 1)),
            _row("CPI", a, date(2026, 9, 1), "moved", date(2026, 9, 1)),
            _row("CPI", b, date(2026, 9, 1), "scheduled", date(2026, 9, 1)),
            _row(
                "PPI", date(2026, 10, 9), date(2026, 10, 5), "scheduled", date(2026, 10, 5)
            ),  # later
        ]
    )
    assert moves.release_days(rows, SESSION) == [("CPI", b, "08:30")]
    # a session before the move still sees the old date (known_from <= S)
    assert moves.release_days(rows, date(2026, 8, 20)) == [("CPI", a, "08:30")]
    assert moves.release_days(None, SESSION) == []


def test_rule_days_are_the_monthly_expiry_and_the_quarter_end() -> None:
    grid = sessions_ending(date(2026, 10, 2), 130)
    found = moves.structure_positions(grid)
    assert date(2026, 9, 18) in [grid[p] for p in found[moves.EXPIRY]]  # the third Friday
    assert [grid[p] for p in found[moves.QUARTER_END]][-1] == date(2026, 9, 30)


def test_class_stats_count_median_and_worst_fall() -> None:
    returns = np.log(np.array([[1.0], [0.9], [1.1], [1.0]]))
    mult = np.array([[np.nan], [2.0], [4.0], [np.nan]])
    n, median, worst = moves.class_stats(mult, returns, [1, 2, 3])
    assert (n[0], median[0]) == (2, 3.0)  # the unknown multiple is not counted
    assert worst[0] == pytest.approx(-0.1)
    n, median, worst = moves.class_stats(mult, returns, [2])
    assert np.isnan(worst[0])  # none fell: UNKNOWN, never zero
    n, median, worst = moves.class_stats(mult, returns, [])
    assert n[0] == 0 and np.isnan(median[0])
