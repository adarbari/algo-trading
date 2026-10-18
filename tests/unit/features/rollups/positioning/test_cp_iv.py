"""``cp_iv@v1``: the open-interest-weighted call-put IV spread over matched pairs, the smirk
(OTM put nearest 0.95 minus the ATM call), the ATM call and put vols, the expiry choice and
every status, on chains priced by Black-Scholes at hand-picked vols."""

from dataclasses import replace
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from algotrade.features.rollups.positioning import cp_iv
from algotrade.quant import black_scholes
from tests.helpers.rollup_store import END, quote_row

R = 0.04
P = cp_iv.CpIvParams()
TARGET = END + timedelta(days=30)


def rows_for(uid, expiry, vols, oi=None, spot=100.0, session=END):
    """``vols``: ``{(right, strike): sigma}``; ``oi``: the open interest per key (default 10)."""
    t = (expiry - session).days / 365
    out = []
    for (right, strike), sigma in vols.items():
        mid = float(black_scholes.price(spot, strike, t, R, 0.0, sigma, right == "C"))
        out.append(
            quote_row(
                uid, session, expiry, right, strike, mid - 0.01, mid + 0.01,
                oi=(oi or {}).get((right, strike), 10.0),
            )
        )  # fmt: skip
    return out


def run(rows, spots, params=P):
    underlyings = pd.DataFrame(
        {"instrument_id": list(spots), "close": list(spots.values()), "price": list(spots.values())}
    )
    inputs = {
        cp_iv.OPTIONS: pd.DataFrame(rows),
        cp_iv.RATES: pd.DataFrame({"tenor_days": [30, 365], "rate_cont": [R, R]}),
        cp_iv.UNDERLYINGS: underlyings,
    }
    return cp_iv.compute(inputs, END, params).set_index("instrument_id")


VOLS = {
    ("C", 95): 0.33, ("P", 95): 0.36,  # diff -0.03, weight 100
    ("C", 100): 0.32, ("P", 100): 0.31,  # no open interest: no weight, but the ATM vols
    ("C", 105): 0.33, ("P", 105): 0.30,  # diff +0.03, weight 300
    ("P", 90): 0.40,  # an OTM put, further from 0.95 than the 95 put
    ("C", 80): 0.50, ("P", 80): 0.20,  # outside the pair band (m = 0.8)
}  # fmt: skip
OI = {
    ("C", 95): 100,
    ("P", 95): 100,
    ("C", 105): 300,
    ("P", 105): 300,
    ("C", 100): 0,
    ("P", 100): 0,
}


def test_spread_smirk_and_atm_vols_on_a_hand_priced_chain() -> None:
    rows = rows_for("EQ:A", TARGET, VOLS, OI)
    rows += rows_for("EQ:A", END + timedelta(days=14), {("C", 100): 0.9, ("P", 100): 0.9})
    out = run(rows, {"EQ:A": 100.0}).loc["EQ:A"]
    assert out["cp_iv_status"] == "OK" and out["cp_iv_dte"] == 30
    assert out["cp_iv_spread"] == pytest.approx((-0.03 * 100 + 0.03 * 300) / 400, abs=1e-4)
    assert out["atm_call_iv"] == pytest.approx(0.32, abs=1e-4)
    assert out["atm_put_iv"] == pytest.approx(0.31, abs=1e-4)
    assert out["iv_smirk"] == pytest.approx(0.36 - 0.32, abs=1e-4)  # the 95 put, not the 90


def test_expiry_is_the_one_nearest_30_days_within_10_to_60() -> None:
    vols = {("C", 100): 0.30, ("P", 100): 0.30}
    rows = rows_for("EQ:A", END + timedelta(days=25), dict.fromkeys(vols, 0.3))
    rows += rows_for("EQ:A", END + timedelta(days=38), dict.fromkeys(vols, 0.5))  # further
    rows += rows_for("EQ:A", END + timedelta(days=5), dict.fromkeys(vols, 0.7))  # under 10
    rows += rows_for("EQ:A", END + timedelta(days=90), dict.fromkeys(vols, 0.8))  # over 60
    out = run(rows, {"EQ:A": 100.0}).loc["EQ:A"]
    assert out["cp_iv_dte"] == 25 and out["atm_call_iv"] == pytest.approx(0.30, abs=1e-4)


def test_statuses_and_null_columns() -> None:
    far_only = rows_for("EQ:NOEXP", END + timedelta(days=90), {("C", 100): 0.3, ("P", 100): 0.3})
    calls_only = rows_for("EQ:NOPAIR", TARGET, {("C", 100): 0.3})
    no_oi = rows_for(
        "EQ:NOOI", TARGET, {("C", 100): 0.3, ("P", 100): 0.3}, {("C", 100): 0, ("P", 100): 0}
    )
    no_spot = rows_for("EQ:NOSPOT", TARGET, {("C", 100): 0.3, ("P", 100): 0.3})
    out = run(
        far_only + calls_only + no_oi + no_spot,
        {"EQ:NOEXP": 100.0, "EQ:NOPAIR": 100.0, "EQ:NOOI": 100.0, "EQ:NOCHAIN": 100.0},
    )
    assert out.loc["EQ:NOEXP", "cp_iv_status"] == "NO_EXPIRY"
    assert out.loc["EQ:NOCHAIN", "cp_iv_status"] == "NO_CHAIN"
    assert out.loc["EQ:NOSPOT", "cp_iv_status"] == "NO_SPOT"
    nopair = out.loc["EQ:NOPAIR"]  # calls only: no spread, no put, but the call vol
    assert nopair["cp_iv_status"] == "NO_PAIRS" and np.isnan(nopair["cp_iv_spread"])
    assert nopair["atm_call_iv"] == pytest.approx(0.3, abs=1e-4)
    assert np.isnan(nopair["atm_put_iv"]) and np.isnan(nopair["iv_smirk"])
    assert out.loc["EQ:NOOI", "cp_iv_status"] == "NO_PAIRS"  # a pair with no weight is none
    assert np.isnan(out.loc["EQ:NOEXP", "atm_call_iv"])  # null, never zero


def test_wide_quotes_are_not_smile_quotes() -> None:
    rows = rows_for("EQ:A", TARGET, {("C", 100): 0.3, ("P", 100): 0.3})
    for row in rows:
        row["ask"] = row["bid"] * 4  # (ask - bid) / mid far above 0.35
    out = run(rows, {"EQ:A": 100.0}).loc["EQ:A"]
    assert out["cp_iv_status"] == "NO_PAIRS" and np.isnan(out["atm_call_iv"])


def test_params_validate() -> None:
    with pytest.raises(ValueError, match="min_days"):
        replace(P, min_days=31)
    with pytest.raises(ValueError, match="atm_band"):
        replace(P, atm_band=0.2)
    with pytest.raises(ValueError, match="otm_lo"):
        replace(P, otm_lo=0.96)
    assert cp_iv.GROUP.table == "rollups/instrument/cp_iv@v1"
