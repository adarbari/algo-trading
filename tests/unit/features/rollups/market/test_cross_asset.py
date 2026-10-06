"""``market_cross_asset@v1`` on stored ETF series: turbulence, absorption ratio and shift
equal ``quant.covariance`` on the basket's log returns in the fixed ticker order, the
leadership ratios by hand, a missing ticker is skipped (``basket_size``) or gives a null
ratio, short histories give nulls, and a permutation of ids changes nothing."""

from collections.abc import Mapping

import numpy as np
import pandas as pd
import pytest

from algotrade.data import StoreReader
from algotrade.features.framework.runner import compute_one, compute_sessions
from algotrade.features.rollups.market import cross_asset as ca
from algotrade.quant.covariance import absorption_ratio, absorption_shift, turbulence
from tests.helpers.rollup_store import END, series, store, write_bars
from tests.helpers.stored_frames import write_reference

GROUP = ca.GROUP
F32 = 2e-7
FULL = ca.LOOKBACK + 1  # sessions the absorption shift needs


def closes_for(tickers: tuple[str, ...], n: int) -> dict[str, np.ndarray]:
    return {t: series(n, seed=i + 1) for i, t in enumerate(tickers)}


def stored(
    closes: Mapping[str, np.ndarray],
    ids: Mapping[str, str] | None = None,
    skip: Mapping[str, list[int]] | None = None,
) -> StoreReader:
    """Bars for each ticker under ``ids[ticker]`` (default ``EQ:<ticker>``; ``skip``: session
    indexes without a bar) and a reference."""
    ids = ids or {t: f"EQ:{t}" for t in closes}
    writer, reader = store()
    gaps = {ids[t]: list(i) for t, i in (skip or {}).items()}
    days = write_bars(writer, {ids[t]: c for t, c in closes.items()}, skip=gaps)
    write_reference(writer, days[0], {t: ids[t] for t in closes})
    return reader


def market_row(reader: StoreReader) -> dict[str, object]:
    frame = compute_one(reader, GROUP, END).frame
    assert frame is not None and list(frame["instrument_id"]) == ["MKT:US"]
    return frame.iloc[0].to_dict()


@pytest.fixture(scope="module")
def full() -> tuple[dict[str, np.ndarray], dict[str, object]]:
    closes = closes_for(ca.TICKERS, FULL)
    return closes, market_row(stored(closes))


def test_stress_equals_quant_on_the_basket_in_ticker_order(
    full: tuple[dict[str, np.ndarray], dict[str, object]],
) -> None:
    closes, row = full
    returns = np.diff(np.log(np.column_stack([closes[t] for t in ca.BASKET])), axis=0)
    ar = absorption_ratio(returns, 500, half_life=250.0)
    assert row["basket_size"] == len(ca.BASKET)
    assert row["turbulence_60d"] == pytest.approx(turbulence(returns, 60)[-1], rel=F32)
    assert row["absorption_ratio_500d"] == pytest.approx(ar[-1], rel=F32)
    assert row["absorption_shift"] == pytest.approx(absorption_shift(ar, 15, 252)[-1], rel=1e-6)
    assert 0 < row["absorption_ratio_500d"] < 1  # type: ignore[operator]


def test_leadership_ratios_by_hand(full: tuple[dict[str, np.ndarray], dict[str, object]]) -> None:
    closes, row = full
    for a, b in ca.RATIOS:
        ca_, cb = closes[a], closes[b]
        want = (ca_[-1] / cb[-1]) / (ca_[-64] / cb[-64]) - 1
        assert row[ca.ratio_column(a, b)] == pytest.approx(want, rel=1e-6), (a, b)


def test_a_missing_ticker_is_skipped_or_gives_a_null_ratio() -> None:
    tickers = tuple(t for t in ca.TICKERS if t not in ("XLF", "RSP", "CPER"))
    closes = closes_for(tickers, 120)
    row = market_row(stored(closes))
    basket = [t for t in ca.BASKET if t != "XLF"]
    returns = np.diff(np.log(np.column_stack([closes[t] for t in basket])), axis=0)
    assert row["basket_size"] == len(ca.BASKET) - 1
    assert row["turbulence_60d"] == pytest.approx(turbulence(returns, 60)[-1], rel=F32)
    # 120 sessions: too short for the absorption ratio and its shift
    assert pd.isna(row["absorption_ratio_500d"]) and pd.isna(row["absorption_shift"])
    assert pd.isna(row["rsp_vs_spy"]) and pd.isna(row["cper_vs_gld"])
    assert row["iwm_vs_spy"] > -1  # type: ignore[operator]


def test_a_small_basket_or_a_short_history_is_null() -> None:
    few = closes_for(("SPY", "QQQ", "IWM", "TLT"), 120)
    row = market_row(stored(few))
    assert row["basket_size"] == 4
    assert all(pd.isna(row[c]) for c in ("turbulence_60d", "absorption_ratio_500d"))
    short = closes_for(ca.TICKERS, 50)
    row = market_row(stored(short))
    assert row["basket_size"] == 0
    assert all(pd.isna(row[c]) for c in ca.COLUMNS if c != "basket_size")


def test_a_permutation_of_ids_changes_nothing() -> None:
    closes = closes_for(ca.BASKET, 120)
    shuffled = dict(zip(ca.BASKET, reversed([f"EQ:ID{i:02d}" for i in range(14)]), strict=True))
    same, permuted = market_row(stored(closes)), market_row(stored(closes, shuffled))
    pd.testing.assert_series_equal(pd.Series(same), pd.Series(permuted), check_exact=True)


@pytest.mark.parametrize(("back", "kept"), [(62, False), (63, True)])
def test_a_ticker_is_skipped_exactly_when_turbulence_would_see_its_gap(
    back: int, kept: bool
) -> None:
    """Turbulence reads 61 returns (62 closes): a gap 62 sessions back skips the ticker, one
    63 back does not reach it."""
    closes = closes_for(ca.BASKET, 120)
    row = market_row(stored(closes, skip={"XLF": [120 - back]}))
    basket = [t for t in ca.BASKET if kept or t != "XLF"]
    returns = np.diff(np.log(np.column_stack([closes[t] for t in basket])), axis=0)
    assert row["basket_size"] == len(basket)
    assert row["turbulence_60d"] == pytest.approx(turbulence(returns, 60)[-1], rel=F32)


def test_backfill_equals_nightly() -> None:
    reader = stored(closes_for(ca.TICKERS, 120))
    sessions = reader.dates("bars/1d")[-4:]
    for result in compute_sessions(reader, GROUP, sessions):
        nightly = compute_one(reader, GROUP, result.session).frame
        assert result.frame is not None and nightly is not None
        pd.testing.assert_frame_equal(result.frame, nightly)
