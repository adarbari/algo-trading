"""``dispersion.mean_member_vol``: the mean realised volatility of the universe's complete stocks
over 21 closes (never a thin sample, never ETFs, never an incomplete window), and the ratio the
conditions group stores from it."""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.rollups.market.edges import conditions as c
from algotrade.features.rollups.market.edges import dispersion as d

END = date(2026, 10, 2)
DAYS = sessions_ending(END, d.CLOSES)


def bars(closes: dict[str, list[float]], days: list[date] = DAYS) -> pd.DataFrame:
    rows = [
        {
            "instrument_id": iid,
            "session_date": day,
            "open": px,
            "high": px,
            "low": px,
            "close": px,
            "volume": 1_000.0,
        }
        for iid, path in closes.items()
        for day, px in zip(days[-len(path) :], path, strict=True)
    ]
    return pd.DataFrame(rows)


def reference(*members: str) -> pd.DataFrame:
    """A reference snapshot saying which ids are in the S&P 500 (the others are not)."""
    ids = ["A", "B", "ETF1", "X"]
    return pd.DataFrame({"instrument_id": ids, "in_sp500": [i in members for i in ids]})


ALL = reference("A", "B", "ETF1")


def universe(stocks: list[str], etfs: tuple[str, ...] = ()) -> pd.DataFrame:
    rows = [{"instrument_id": s, "asset_class": "STOCK"} for s in stocks]
    return pd.DataFrame(rows + [{"instrument_id": e, "asset_class": "ETF"} for e in etfs])


def zigzag(step: float) -> list[float]:
    """21 closes alternating up and down by ``step`` (a constant return magnitude)."""
    out = [100.0]
    for i in range(20):
        out.append(out[-1] * np.exp(step if i % 2 == 0 else -step))
    return out


def test_the_mean_is_over_complete_stock_members_only() -> None:
    paths = {"A": zigzag(0.01), "B": zigzag(0.03), "ETF1": zigzag(0.5)}
    got = d.mean_member_vol(universe(["A", "B"], ("ETF1",)), ALL, bars(paths), END, 2)
    expected = np.mean([0.01, 0.03]) * np.sqrt(252) * np.sqrt(20 / 19) * 1.0
    assert abs(got - expected) / expected < 0.2  # sample stdev of +-step alternating returns
    assert d.mean_member_vol(universe(["A"], ("ETF1",)), ALL, bars(paths), END, 1) < got


def test_a_member_with_a_gap_is_left_out_and_a_thin_sample_is_unknown() -> None:
    gap = bars({"A": zigzag(0.01), "B": zigzag(0.02)})
    gap = gap[~((gap["instrument_id"] == "B") & (gap["session_date"] == DAYS[10]))]
    only_a = d.mean_member_vol(universe(["A", "B"]), ALL, gap, END, 1)
    assert only_a == d.mean_member_vol(universe(["A"]), ALL, bars({"A": zigzag(0.01)}), END, 1)
    assert np.isnan(d.mean_member_vol(universe(["A", "B"]), ALL, gap, END, 2))


def test_no_universe_or_bars_is_unknown() -> None:
    assert np.isnan(d.mean_member_vol(None, ALL, bars({"A": zigzag(0.01)}), END, 1))
    assert np.isnan(d.mean_member_vol(universe(["A"]), ALL, None, END, 1))
    assert np.isnan(d.mean_member_vol(universe(["A"]), ALL, pd.DataFrame(), END, 1))


def test_bars_after_the_session_are_ignored() -> None:
    later = sessions_ending(date(2026, 10, 9), d.CLOSES + 5)
    base = d.mean_member_vol(universe(["A"]), ALL, bars({"A": zigzag(0.01)}), END, 1)
    path = zigzag(0.01) + [500.0] * 5
    assert d.mean_member_vol(universe(["A"]), ALL, bars({"A": path}, later), END, 1) == base
    assert (
        abs(base - d.mean_member_vol(universe(["A"]), ALL, bars({"A": zigzag(0.01)}), END, 1))
        < 1e-12
    )


def test_the_ratio_is_index_over_members_and_unknown_without_either() -> None:
    assert c.corr_ratio(0.1, 0.2) == 0.5
    assert np.isnan(c.corr_ratio(np.nan, 0.2)) and np.isnan(c.corr_ratio(0.1, np.nan))
    assert np.isnan(c.corr_ratio(0.1, 0.0))


def test_only_sp500_stocks_in_the_reference_snapshot_count() -> None:
    paths = {"A": zigzag(0.01), "X": zigzag(0.05)}
    only_a = d.mean_member_vol(universe(["A", "X"]), reference("A"), bars(paths), END, 1)
    assert only_a == d.mean_member_vol(universe(["A"]), reference("A"), bars(paths), END, 1)
    both = d.mean_member_vol(universe(["A", "X"]), reference("A", "X"), bars(paths), END, 1)
    assert both > only_a
    assert np.isnan(d.mean_member_vol(universe(["A"]), None, bars(paths), END, 1))
    no_flag = reference("A").drop(columns="in_sp500")
    assert np.isnan(d.mean_member_vol(universe(["A"]), no_flag, bars(paths), END, 1))
