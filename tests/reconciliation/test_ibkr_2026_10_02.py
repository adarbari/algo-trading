"""Reconcile our features for session 2026-10-02 against IBKR (recorded 2026-10-03, read-only).

Our side is recomputed here from the RAW recorded inputs (unadjusted ``bars/1d``, split and
dividend events) with production code: ``data.prices.adjust_bars`` ("splits"), the
``price_stats@v2`` and ``dividends@v2`` groups' ``compute`` (through their ``FeatureGroup``),
the site's ``div_yield`` expression feature and ``quant.realized_vol``. ``iv30`` is the value
we stored that night (recomputing it needs the full option chains). Fixtures and their
meaning: ``tests/fixtures/reconciliation/ibkr_2026-10-02/README.md``; what this proves and the
tolerances: ``docs/testing.md``.
"""

import json
import math
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from algotrade.data.prices import adjust_bars
from algotrade.features.rollups.corporate import dividends
from algotrade.features.rollups.price import price_stats
from algotrade.features.site import site_features
from algotrade.quant import realized_vol
from algotrade.storage.configs.files import FileConfigStore

pytestmark = pytest.mark.reconciliation

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "reconciliation" / "ibkr_2026-10-02"
CONFIG = Path(__file__).resolve().parents[2] / "config"
SESSION = date(2026, 10, 2)
TICKERS = ("AAPL", "SPY", "KO", "TQQQ", "TSM", "RPGL")

CLOSE_REL = 0.002  # split-adjusted closes (RPGL's IBKR closes are rounded around its split)
RANGE_REL = 0.001  # daily highs / lows
HV_REL = 0.005  # hv20 vs close-to-close HV20 recomputed from IBKR closes
HIGH_52W_REL = 0.0005  # 52-week high where no dividend adjustment applies
HIGH_52W_EXACT = ("AAPL", "SPY", "RPGL")  # no ex-date moved the high (none since, or no payer)
EXTREME_REL = 0.0005  # slack on "ours >= IBKR" for the dividend-adjusted 52-week extremes
YIELD_ABS = 0.0005  # dividend yield, decimal (0.05 percentage points)
IV_ABS = 0.025  # implied vol, decimal (2.5 vol points)


def _csv(name: str) -> pd.DataFrame:
    return pd.read_csv(FIXTURES / name)


def _events(name: str) -> pd.DataFrame:
    frame = _csv(name).rename(columns={"ticker": "instrument_id"})
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    return frame.assign(event_date=frame["ts"].dt.date)


@pytest.fixture(scope="module")
def ibkr() -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / "ibkr.json").read_text())
    return data


@pytest.fixture(scope="module")
def adjusted() -> pd.DataFrame:
    """Our raw bars, split-adjusted as of the session (every split is on or before it)."""
    raw = _csv("our_bars_1d_raw.csv").rename(columns={"ticker": "instrument_id"})
    raw["session_date"] = pd.to_datetime(raw["session_date"]).dt.date
    raw["ts"] = pd.to_datetime(raw["session_date"]).dt.tz_localize("UTC") + pd.Timedelta(hours=20)
    raw = raw.sort_values(["instrument_id", "ts"], kind="stable").reset_index(drop=True)
    no_dividends = pd.DataFrame(columns=["instrument_id", "ts", "cash_amount"])
    return adjust_bars(raw, _events("our_split_events.csv"), no_dividends, "splits")


@pytest.fixture(scope="module")
def stats(adjusted: pd.DataFrame) -> pd.DataFrame:
    group = price_stats.GROUP
    frame = group.compute({price_stats.BARS: adjusted}, SESSION, group.params)
    return frame.set_index("instrument_id")


@pytest.fixture(scope="module")
def divs(stats: pd.DataFrame) -> pd.DataFrame:
    group = dividends.GROUP
    inputs = {
        dividends.PRICE_STATS: stats.reset_index().assign(session_date=SESSION),
        dividends.DIVIDENDS: _events("our_dividend_events.csv"),
        dividends.SPLITS: _events("our_split_events.csv"),
    }
    out = group.compute(inputs, SESSION, group.params)
    frames = {
        dividends.PRICE_STATS: stats.reset_index().assign(session_date=SESSION),
        dividends.GROUP.table: out.assign(session_date=SESSION),
    }
    yields = site_features(FileConfigStore(CONFIG)).evaluate(frames, ["div_yield"], ["div_yield"])
    return out.merge(yields[["instrument_id", "div_yield"]], on="instrument_id").set_index(
        "instrument_id"
    )


def _ours_on_ibkr_dates(adjusted: pd.DataFrame, ibkr: dict[str, Any], ticker: str) -> pd.DataFrame:
    days = [date.fromisoformat(d) for d in ibkr["dates"]]
    rows = adjusted[adjusted["instrument_id"] == ticker].set_index("session_date")
    missing = sorted(set(days) - set(rows.index))
    assert not missing, f"{ticker}: our bars miss IBKR dates {missing}"
    return rows.loc[days]


def _rel(ours: float, theirs: float) -> float:
    return abs(ours - theirs) / abs(theirs)


@pytest.mark.parametrize("ticker", TICKERS)
def test_split_adjusted_closes_match(adjusted: pd.DataFrame, ibkr: dict, ticker: str) -> None:
    ours = _ours_on_ibkr_dates(adjusted, ibkr, ticker)["close"].to_numpy()
    theirs = ibkr["bars"][ticker]["close"]
    for day, o, t in zip(ibkr["dates"], ours, theirs, strict=True):
        assert _rel(o, t) <= CLOSE_REL, f"{ticker} {day}: close ours {o:.4f} vs IBKR {t:.4f}"


@pytest.mark.parametrize("ticker", [t for t in TICKERS if t != "RPGL"])  # RPGL: closes only
@pytest.mark.parametrize("field", ["high", "low"])
def test_daily_ranges_match(adjusted: pd.DataFrame, ibkr: dict, ticker: str, field: str) -> None:
    ours = _ours_on_ibkr_dates(adjusted, ibkr, ticker)[field].to_numpy()
    theirs = ibkr["bars"][ticker][field]
    for day, o, t in zip(ibkr["dates"], ours, theirs, strict=True):
        assert _rel(o, t) <= RANGE_REL, f"{ticker} {day}: {field} ours {o:.4f} vs IBKR {t:.4f}"


@pytest.mark.parametrize("ticker", TICKERS)
def test_hv20_matches_close_to_close_on_ibkr_closes(
    stats: pd.DataFrame, ibkr: dict, ticker: str
) -> None:
    ours = float(stats.loc[ticker, "hv20"])
    theirs = float(realized_vol.close_to_close(ibkr["bars"][ticker]["close"], 20)[-1])
    message = f"{ticker}: hv20 ours {ours:.5f} vs from IBKR closes {theirs:.5f}"
    assert _rel(ours, theirs) <= HV_REL, message


@pytest.mark.parametrize("ticker", HIGH_52W_EXACT)
def test_52w_high_matches_where_no_dividend_adjustment(
    stats: pd.DataFrame, ibkr: dict, ticker: str
) -> None:
    ours = float(stats.loc[ticker, "high_52w"])
    theirs = ibkr["snapshot"][ticker]["high_52w"]
    assert _rel(ours, theirs) <= HIGH_52W_REL, f"{ticker}: high_52w ours {ours} vs IBKR {theirs}"


@pytest.mark.parametrize("ticker", TICKERS)
@pytest.mark.parametrize("column", ["high_52w", "low_52w"])
def test_52w_extremes_are_split_only(
    stats: pd.DataFrame, divs: pd.DataFrame, ibkr: dict, ticker: str, column: str
) -> None:
    """IBKR scales bars before each ex-date down by the dividend; we do not (split-only, the
    owner's decision of 2026-10-03). So ours is at or above IBKR's, by at most the dividends
    paid since that bar: never more than the trailing-12-month total."""
    ours = float(stats.loc[ticker, column])
    theirs = ibkr["snapshot"][ticker][column]
    div_ttm = float(divs.loc[ticker, "div_ttm"])
    message = f"{ticker}: {column} ours {ours} vs IBKR {theirs} (div_ttm {div_ttm:.4f})"
    assert ours >= theirs * (1 - EXTREME_REL), message
    assert ours - theirs <= div_ttm + theirs * EXTREME_REL, message


@pytest.mark.parametrize("ticker", TICKERS)
def test_dividend_yield_matches(divs: pd.DataFrame, ibkr: dict, ticker: str) -> None:
    ours = float(divs.loc[ticker, "div_yield"])
    theirs = ibkr["snapshot"][ticker]["div_yield"]
    assert abs(ours - theirs) <= YIELD_ABS, f"{ticker}: div_yield ours {ours:.5f} vs IBKR {theirs}"


def test_iv30_recorded_matches_ibkr(ibkr: dict) -> None:
    recorded = _csv("our_iv30_recorded.csv").set_index("ticker")
    compared = 0
    for ticker in TICKERS:
        theirs = ibkr["snapshot"][ticker]["iv"]
        if theirs is None:
            assert ticker not in recorded.index or math.isnan(recorded.loc[ticker, "iv30"])
            continue
        ours = float(recorded.loc[ticker, "iv30"])
        assert recorded.loc[ticker, "iv30_status"] == "OK", ticker
        assert abs(ours - theirs) <= IV_ABS, f"{ticker}: iv30 ours {ours:.4f} vs IBKR {theirs:.4f}"
        compared += 1
    assert compared == 5


def test_rpgl_split_is_why_adjustment_matters(adjusted: pd.DataFrame, ibkr: dict) -> None:
    """Guard on the fixture: RPGL's raw closes jump across its 1-for-16 reverse split, so the
    close test above really exercises the split adjustment."""
    raw = _csv("our_bars_1d_raw.csv").set_index(["ticker", "session_date"])["close"]
    before, after = raw[("RPGL", "2026-09-24")], raw[("RPGL", "2026-09-25")]
    assert after / before > 10
    ours = _ours_on_ibkr_dates(adjusted, ibkr, "RPGL")["close"].to_numpy()
    assert np.all(np.isfinite(ours))
