"""``grid``: the session grid stops before the frozen period and the eligible names are the
stocks over the floors."""

from datetime import date

import pandas as pd

from algotrade.core.time.calendar import sessions_between
from algotrade.services.evaluation.discovery.grid import grid_sessions, pick_eligible
from tests.unit.services.evaluation.discovery.conftest import settings

FIRST_BAR = date(2010, 1, 4)


def test_grid_closes_before_frozen() -> None:
    """Every grid session's window (horizon sessions long) closes before ``frozen_from``, and
    the next grid step would not: the study never labels with the frozen period. Catches: a grid
    that runs to the purge cutoff inclusive, or past it."""
    s = settings()
    grid = grid_sessions(FIRST_BAR, s)
    assert grid and len(grid) > 40
    for g in grid:
        window_end = sessions_between(g.session, s.frozen_from)[s.horizon_sessions]
        assert window_end < s.frozen_from
    last = sessions_between(grid[-1].session, s.frozen_from)
    assert s.step_sessions + s.horizon_sessions >= len(last) - 1  # one more step: too late


def test_grid_starts_after_the_minimum_history_and_steps_evenly() -> None:
    """The first session has ``min_history_sessions`` sessions of bars before it and each next
    is ``step_sessions`` later; blocks count ``block_sessions`` sessions from the first. Catches:
    an off-by-one in the first session or the block index."""
    s = settings()
    grid = grid_sessions(FIRST_BAR, s)
    days = sessions_between(FIRST_BAR, grid[-1].session)
    assert days.index(grid[0].session) == s.min_history_sessions
    assert [days.index(g.session) for g in grid[:3]] == [252, 315, 378]
    assert [g.block for g in grid[:9]] == [0] * 8 + [1]  # 8 steps of 63 span 504 sessions


def test_a_short_history_gives_no_grid_session() -> None:
    """Fewer sessions than the minimum history: an empty grid, not a session without history.
    Catches: a grid starting before the history is long enough."""
    assert grid_sessions(date(2025, 1, 2), settings()) == []


def test_eligible_are_stocks_over_the_price_and_dollar_volume_floors_with_a_bar() -> None:
    """ETFs, penny stocks, thin names and names with no bar (NaN) are out; the age is from the
    listing's start date. Catches: a floor applied to the wrong side, an ETF among the stocks, or
    a missing bar passing a floor."""
    s = settings()
    day = date(2015, 6, 1)
    listings = pd.DataFrame(
        {
            "instrument_id": ["S1", "S2", "S3", "S4", "S5", "E1"],
            "asset_type": ["Stock", "Stock", "Stock", "Stock", "Stock", "ETF"],
            "start_date": [date(2005, 6, 1)] * 6,
        }
    )
    prices = pd.DataFrame(
        {
            "instrument_id": ["S1", "S2", "S3", "S4", "E1"],  # S5 has no price row at all
            "close": [5.0, 4.99, 50.0, None, 50.0],
            "adv": [1_000_000.0, 9e6, 999_999.0, 9e6, 9e6],
            "hv": [0.3, 0.3, 0.3, 0.3, 0.3],
        }
    )
    got = pick_eligible(listings, prices, day, s).names
    assert got["instrument_id"].tolist() == ["S1"]  # S2 < $5, S3 < $1M, S4 no bar, E1 an ETF
    assert abs(got["age_years"].iloc[0] - 10.0) < 0.01
