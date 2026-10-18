"""``cef_nav@v1``: a closed-end fund's discount to NAV on the NAV's own date, and its z-score
against the fund's year; null (never zero) when the NAV is stale, a bar or history is missing."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from algotrade.core.time.calendar import next_session, previous_session, sessions_ending
from algotrade.features.rollups.reference import cef_nav
from algotrade.features.rollups.reference.cef_nav import MIN_OBSERVATIONS, WINDOW, compute

SESSION = date(2026, 10, 16)
FUND, OTHER = "EQ:FUND", "EQ:OTHER"
DAYS = sessions_ending(SESSION, WINDOW)


def _nav(rows: list[tuple[str, date, float, date | None]]) -> pd.DataFrame:
    """``(fund, NAV date, nav, known_from)``; known_from defaults to the next session."""
    return pd.DataFrame(
        [
            {"instrument_id": i, "ts": pd.Timestamp(d, tz="UTC"), "series": "nav", "nav": n,
             "known_from": k or next_session(d), "session_date": k or next_session(d)}
            for i, d, n, k in rows
        ]
    )  # fmt: skip


def _bars(close: dict[tuple[str, date], float]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"instrument_id": i, "session_date": d, "close": c} for (i, d), c in close.items()]
    )


def _row(navs: pd.DataFrame, bars: pd.DataFrame | None, fund: str = FUND) -> pd.Series:
    out = compute({cef_nav.NAV: navs, cef_nav.BARS: bars}, SESSION, None)
    return out.set_index("instrument_id").loc[fund]


def test_the_discount_pairs_the_nav_with_the_close_of_its_own_date() -> None:
    nav_day = previous_session(SESSION)
    bars = _bars({(FUND, nav_day): 9.0, (FUND, SESSION): 20.0})  # the session's close is not used
    row = _row(_nav([(FUND, nav_day, 10.0, None)]), bars)
    assert row["cef_discount_to_nav"] == pytest.approx(-0.10)
    assert row["nav_per_share"] == pytest.approx(10.0) and row["nav_date"] == nav_day


def test_a_premium_is_positive() -> None:
    nav_day = previous_session(SESSION)
    row = _row(_nav([(FUND, nav_day, 10.0, None)]), _bars({(FUND, nav_day): 11.5}))
    assert row["cef_discount_to_nav"] == pytest.approx(0.15)


def test_a_nav_known_later_is_not_in_the_frame_the_input_hands_over() -> None:
    """The input keeps rows by known_from, so compute sees only what the session may know; a NAV
    restated after it replaces the original only where the restated row is the one handed over."""
    nav_day = previous_session(SESSION)
    navs = _nav([(FUND, nav_day, 10.0, None), (FUND, nav_day, 8.0, SESSION)])
    row = _row(navs, _bars({(FUND, nav_day): 9.0}))
    assert row["nav_per_share"] == pytest.approx(8.0)  # the restated version is the later one
    assert row["cef_discount_to_nav"] == pytest.approx(9.0 / 8.0 - 1)


def test_a_stale_nav_has_no_current_discount() -> None:
    old = DAYS[-8]  # more than 5 sessions before the session
    row = _row(_nav([(FUND, old, 10.0, None)]), _bars({(FUND, old): 9.0}))
    assert pd.isna(row["cef_discount_to_nav"]) and row["nav_date"] == old


def test_a_missing_bar_or_a_non_positive_nav_is_null_never_zero() -> None:
    nav_day = previous_session(SESSION)
    assert pd.isna(_row(_nav([(FUND, nav_day, 10.0, None)]), _bars({(OTHER, nav_day): 9.0}))[
        "cef_discount_to_nav"])  # fmt: skip
    assert pd.isna(_row(_nav([(FUND, nav_day, 0.0, None)]), _bars({(FUND, nav_day): 9.0}))[
        "cef_discount_to_nav"])  # fmt: skip
    assert pd.isna(_row(_nav([(FUND, nav_day, 10.0, None)]), None)["cef_discount_to_nav"])


def _history(n: int) -> pd.DataFrame:
    """``n`` NAV dates ending the day before the session at a 5% discount, the last at 15%."""
    days = DAYS[-n - 1 : -1]
    navs = _nav([(FUND, d, 10.0, None) for d in days])
    closes = {(FUND, d): 9.5 for d in days[:-1]}
    closes[(FUND, days[-1])] = 8.5
    return navs, _bars(closes)  # type: ignore[return-value]


def test_the_z_score_is_the_discount_against_the_funds_own_year() -> None:
    navs, bars = _history(MIN_OBSERVATIONS)
    row = _row(navs, bars)
    seen = np.array([-0.05] * (MIN_OBSERVATIONS - 1) + [-0.15])
    expected = (-0.15 - seen.mean()) / seen.std(ddof=1)
    assert row["cef_discount_zscore"] == pytest.approx(expected) and expected < -5


def test_too_few_discounts_or_no_spread_leave_the_z_score_null() -> None:
    navs, bars = _history(MIN_OBSERVATIONS - 1)
    assert pd.isna(_row(navs, bars)["cef_discount_zscore"])
    assert _row(navs, bars)["cef_discount_to_nav"] == pytest.approx(-0.15)  # the discount stands
    days = DAYS[-MIN_OBSERVATIONS - 1 : -1]
    flat = _row(_nav([(FUND, d, 10.0, None) for d in days]), _bars({(FUND, d): 9.0 for d in days}))
    assert pd.isna(flat["cef_discount_zscore"])


def test_no_nav_in_the_window_is_no_row() -> None:
    out = compute({cef_nav.NAV: _nav([(FUND, DAYS[0] - pd.Timedelta(days=30), 10.0, None)]),
                   cef_nav.BARS: None}, SESSION, None)  # fmt: skip
    assert out.empty and list(out.columns) == ["instrument_id", *cef_nav.COLUMNS]
