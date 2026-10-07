"""The wing search ``put_wing@v1`` and ``call_wing@v1`` share: both rights computed on the same
chain, the right flag reaching the pricing (put-call delta parity), the tie-break and yield
each side declares, the documented columns built from the side and the bands, and the base
parameters' validation."""

from dataclasses import replace
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from algotrade.features.rollups.options import call_wing as cw
from algotrade.features.rollups.options import put_wing as pw
from algotrade.features.rollups.options import wing_search as ws
from algotrade.quant.rates import YieldCurve
from tests.helpers.rollup_store import END, chain_rows

E45 = END + timedelta(days=45)
STRIKES = tuple(range(50, 151))


def _inputs(rows: list[dict[str, object]], spot: float) -> dict[str, pd.DataFrame]:
    return {
        pw.OPTIONS: pd.DataFrame(rows),
        pw.RATES: pd.DataFrame({"tenor_days": [30, 365], "rate_cont": [0.04, 0.04]}),
        pw.UNDERLYINGS: pd.DataFrame({"instrument_id": ["EQ:A"], "price": [spot], "iv30": 30.0}),
    }


def test_both_wings_on_the_same_chain_see_their_own_right_and_share_the_expiry() -> None:
    rows = chain_rows("EQ:A", END, 100.0, {E45: 0.4}, 0.04, strikes=STRIKES)
    inputs = _inputs(rows, 100.0)
    put = pw.compute(inputs, END, pw.PutWingParams()).set_index("instrument_id").loc["EQ:A"]
    call = cw.compute(inputs, END, cw.CallWingParams()).set_index("instrument_id").loc["EQ:A"]
    assert (put["wing_status"], call["wing_status"]) == ("OK", "OK")
    assert (put["target_expiry"], put["target_dte"]) == (call["target_expiry"], call["target_dte"])
    assert put["best_put_delta"] < 0 < call["best_call_delta"]  # the puts' deltas are negative
    assert 0.08 <= -put["best_put_delta"] <= 0.15 and 0.15 <= call["best_call_delta"] <= 0.30
    assert put["best_put_strike"] < 100.0 < call["best_call_strike"]  # OTM on its own side
    assert put["best_put_roc"] == pytest.approx(put["best_put_mid"] / put["best_put_strike"])
    assert call["best_call_yield"] == pytest.approx(call["best_call_mid"] / 100.0)
    assert not [c for c in put.index if "call" in c] and not [c for c in call.index if "put" in c]
    # The call wing's columns are the put wing's, mirrored (the ROC becomes the yield).
    mirrored = [
        c.replace("best_put_roc", "best_put_yield").replace("put", "call") for c in pw.COLUMNS
    ]
    assert mirrored == list(cw.COLUMNS)


def test_the_right_reaches_the_pricing_put_call_delta_parity() -> None:
    """At one vol and strike, delta(call) - delta(put) = exp(-q t) (here q = 0, t = 45/365 and
    r from the curve): the same contracts priced as calls and as puts differ by exactly that."""
    curve = YieldCurve.from_days(pd.Series([30, 365]), pd.Series([0.04, 0.04]))
    rows = pd.DataFrame(chain_rows("EQ:A", END, 100.0, {E45: 0.4}, 0.04, strikes=(90, 100, 110)))
    base = rows.assign(spot=100.0, q=0.0, dte=45)
    calls = ws.our_deltas(base[base["right"] == "C"], curve, True)
    puts = ws.our_deltas(base[base["right"] == "P"], curve, False)
    assert np.allclose(calls["iv"], 0.4, atol=1e-6) and np.allclose(puts["iv"], 0.4, atol=1e-6)
    assert np.allclose(calls["delta"].to_numpy() - puts["delta"].to_numpy(), 1.0, atol=1e-6)


def test_each_side_ranks_by_its_own_yield_and_breaks_ties_its_own_way() -> None:
    frame = pd.DataFrame(
        {
            "strike": [100.0, 110.0, 120.0],
            "bid": 1.0,
            "ask": 1.1,
            "mid": [1.0, 1.0, 1.0],
            "iv": 0.4,
            "delta": [0.2, 0.2, 0.2],
            "open_interest": [7.0, 7.0, 7.0],
            "volume": 5.0,
            "spot": [50.0, 50.0, 50.0],
        }
    )
    call = ws.wing_row(frame, cw.CallWingParams(), cw.SIDE)
    put = ws.wing_row(frame.assign(delta=-0.1), pw.PutWingParams(), pw.SIDE)
    assert call["best_call_yield"] == pytest.approx(1.0 / 50.0)  # per dollar of stock
    assert call["best_call_strike"] == 120.0  # an exact tie: the higher strike
    assert put["best_put_roc"] == pytest.approx(1.0 / 100.0)  # per strike: 100 has the most
    assert put["best_put_strike"] == 100.0  # (and an exact tie would go to the lower strike)


def test_the_columns_are_built_from_the_side_and_the_bands() -> None:
    features = {f.name: f for f in ws.wing_features(cw.SIDE, cw.CallWingParams())}
    assert features["best_call_delta"].valid_range == (0.05, 0.50)
    assert features["delta_band_distance"].valid_range == (0, 0.2)
    assert features["target_dte"].valid_range == (30, 60)
    assert "0.15..0.30" in features["n_strikes"].description
    assert "higher strike" in features["best_call_strike"].description
    assert features["best_call_yield"].dtype == "float32"
    assert features["best_call_yield"].unit == "decimal"
    puts = {f.name: f for f in ws.wing_features(pw.SIDE, pw.PutWingParams())}
    assert puts["best_put_delta"].valid_range == (-0.35, -0.05)
    assert "0.08..0.15" in puts["wing_oi"].description
    assert "lower strike" in puts["best_put_strike"].description
    assert [f.name for f in pw.FEATURES] == list(puts) and [f.name for f in cw.FEATURES] == list(
        features
    )


def test_wing_params_need_their_bands_and_validate_them() -> None:
    with pytest.raises(TypeError, match="delta_lo"):
        ws.WingParams()  # type: ignore[call-arg]
    base = ws.WingParams(delta_lo=0.1, delta_hi=0.2, search_lo=0.05, search_hi=0.4)
    assert (base.dte_min, base.dte_target, base.dte_max, base.prefer_monthly) == (30, 45, 60, True)
    with pytest.raises(ValueError, match="dte_min"):
        replace(base, dte_target=20)
    with pytest.raises(ValueError, match="delta_lo"):
        replace(base, search_lo=0.15)
