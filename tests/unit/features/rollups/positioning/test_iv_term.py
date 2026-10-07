"""``iv_term@v1`` on chains priced by Black-Scholes with known flat vols: the vol at the next
expiry, the constant 90-day vol interpolated in total variance (standard monthlies around 90
days), a single usable expiry is not a 90-day vol, every status with partial values kept,
the spot rule, and the params."""

from dataclasses import replace
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from algotrade.features.framework.runner import compute_one
from algotrade.features.rollups.positioning import iv_term as it
from algotrade.quant.implied_vol import interpolate_total_variance
from tests.helpers.rollup_store import END, chain_rows, quote_row, store, write_chains, write_curve

GROUP = it.GROUP
P = it.IvTermParams()
R = 0.04
NEXT = END + timedelta(days=7)
DEC, JAN = END + timedelta(days=77), END + timedelta(days=105)  # third Fridays around 90 days
NOV = END + timedelta(days=49)


def run(rows, spots, close=True):
    underlyings = pd.DataFrame(
        {
            "instrument_id": list(spots),
            "close": list(spots.values()) if close else np.nan,
            "price": list(spots.values()),
        }
    )
    inputs = {
        it.OPTIONS: pd.DataFrame(rows),
        it.RATES: pd.DataFrame({"tenor_days": [30, 365], "rate_cont": [R, R]}),
        it.UNDERLYINGS: underlyings,
    }
    return it.compute(inputs, END, P).set_index("instrument_id")


def chain(uid, vols, **kwargs):
    return chain_rows(uid, END, 100.0, vols, R, **kwargs)


def test_next_expiry_vol_and_the_90_day_vol_in_total_variance() -> None:
    rows = chain("EQ:A", {NEXT: 0.50, NOV: 0.34, DEC: 0.30, JAN: 0.26})
    a = run(rows, {"EQ:A": 100.0}).loc["EQ:A"]
    assert a["iv_term_status"] == "OK"
    assert a["iv_next"] == pytest.approx(0.50, abs=2e-3)  # the 7-day expiry, not interpolated
    expected = float(interpolate_total_variance(77 / 365, 0.30, 105 / 365, 0.26, 90 / 365))
    assert a["iv_90d"] == pytest.approx(expected, abs=2e-3)
    assert 0.26 < a["iv_90d"] < 0.30
    assert (a["iv_next"] / 0.30) > 1.2  # an event-sized premium in the front expiry


def test_a_single_expiry_in_the_window_is_not_a_90_day_vol() -> None:
    rows = chain("EQ:A", {NEXT: 0.50, NOV: 0.34})  # 49 days is the only expiry in 30..180
    a = run(rows, {"EQ:A": 100.0}).loc["EQ:A"]
    assert a["iv_term_status"] == "NO_90D" and np.isnan(a["iv_90d"])
    assert a["iv_next"] == pytest.approx(0.50, abs=2e-3)  # the next expiry keeps its value


def test_every_status_keeps_the_side_that_exists() -> None:
    wide = chain("EQ:NONEXT", {NEXT: 0.5}, spread=50.0) + chain("EQ:NONEXT", {DEC: 0.3, JAN: 0.26})
    only_wide = chain("EQ:NEITHER", {NEXT: 0.5, DEC: 0.3, JAN: 0.26}, spread=50.0)
    rows = [
        *chain("EQ:OK", {NEXT: 0.5, DEC: 0.3, JAN: 0.26}),
        *chain("EQ:SHORT", {NEXT: 0.5, NOV: 0.34}),
        *wide,
        *only_wide,
        *chain("EQ:NOSPOT", {NEXT: 0.5, DEC: 0.3, JAN: 0.26}),
    ]
    spots = dict.fromkeys(("EQ:OK", "EQ:SHORT", "EQ:NONEXT", "EQ:NEITHER", "EQ:NOCHAIN"), 100.0) | {
        "EQ:NOSPOT": np.nan
    }
    out = run(rows, spots)
    assert out["iv_term_status"].to_dict() == {
        "EQ:NEITHER": "NO_NEXT",  # the first failing step when both are missing
        "EQ:NOCHAIN": "NO_CHAIN",
        "EQ:NONEXT": "NO_NEXT",
        "EQ:NOSPOT": "NO_SPOT",
        "EQ:OK": "OK",
        "EQ:SHORT": "NO_90D",
    }
    assert np.isnan(out.loc["EQ:NONEXT", "iv_next"])
    assert out.loc["EQ:NONEXT", "iv_90d"] == pytest.approx(0.28, abs=0.02)  # partial value kept
    assert out.loc["EQ:NEITHER", ["iv_next", "iv_90d"]].isna().all()
    assert out.loc[["EQ:NOSPOT", "EQ:NOCHAIN"], ["iv_next", "iv_90d"]].isna().all().all()


def test_spot_is_the_close_then_the_price() -> None:
    rows = chain("EQ:A", {NEXT: 0.5, DEC: 0.3, JAN: 0.26})
    assert run(rows, {"EQ:A": 100.0}, close=False).loc["EQ:A", "iv_term_status"] == "OK"
    stale = pd.DataFrame({"instrument_id": ["EQ:A"], "close": [100.0], "price": [160.0]})
    inputs = {
        it.OPTIONS: pd.DataFrame(rows),
        it.RATES: pd.DataFrame({"tenor_days": [30], "rate_cont": [R]}),
        it.UNDERLYINGS: stale,
    }
    out = it.compute(inputs, END, P).set_index("instrument_id").loc["EQ:A"]
    assert out["iv_next"] == pytest.approx(0.5, abs=2e-3)  # the close sets the strikes around F


def test_params_share_iv30s_checks_and_the_filters_apply() -> None:
    with pytest.raises(ValueError, match="min_days"):
        replace(P, min_days=100)
    illiquid = [
        quote_row("EQ:A", END, NEXT, r, float(k), 0.05, 5.0, volume=0, oi=0)
        for r in "CP"
        for k in (95, 100, 105)
    ]
    out = run(illiquid, {"EQ:A": 100.0})  # no open interest, no volume: filtered out
    assert out.loc["EQ:A", "iv_term_status"] == "NO_NEXT"


def test_a_session_reads_only_its_chain_partition() -> None:
    writer, reader = store()
    for day, sigma in ((END - timedelta(days=1), 0.2), (END, 0.6)):
        vols = {day + timedelta(days=7): sigma}
        write_chains(writer, day, chain_rows("EQ:A", day, 100.0, vols, R), {"EQ:A": 100.0})
        write_curve(writer, day, R)
    first = compute_one(reader, GROUP, END - timedelta(days=1)).frame
    second = compute_one(reader, GROUP, END).frame
    assert first is not None and second is not None
    assert first.iloc[0]["iv_next"] == pytest.approx(0.2, abs=2e-3)
    assert second.iloc[0]["iv_next"] == pytest.approx(0.6, abs=2e-3)
    assert GROUP.table == "rollups/instrument/iv_term@v1"
