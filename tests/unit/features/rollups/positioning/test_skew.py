"""``skew@v1``: the OP3 worked example (skew 0.208, the term step 0.3198), delta bracketing
with no extrapolation, a skewed chain read against a root-found 25-delta strike, the next
expiry, every status, the spot rule and point in time through the runner."""

from dataclasses import replace
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from algotrade.features.framework.runner import compute_one
from algotrade.features.rollups.options.iv30 import term_vol
from algotrade.features.rollups.positioning import skew as sk
from algotrade.quant import black_scholes
from tests.helpers.rollup_store import (
    END,
    chain_rows,
    quote_row,
    store,
    write_chains,
    write_curve,
)

GROUP = sk.GROUP
P = sk.SkewParams()
R = 0.04
NEAR, FAR = END + timedelta(days=14), END + timedelta(days=49)  # both third Fridays
WEEKLY = END + timedelta(days=3)  # the next expiry


def line(sigma0: float, slope: float):
    """A smile linear in strike: ``sigma(K) = sigma0 + slope (K - 100)``."""
    return lambda k: sigma0 + slope * (k - 100.0)


def smile_chain(uid, expiries, smile, spot=100.0, strikes=range(60, 141), session=END):
    """Quotes priced by Black-Scholes at ``smile(K)``, bid / ask 0.02 around the mid."""
    rows = []
    for expiry in expiries:
        t = (expiry - session).days / 365
        for k in strikes:
            for right in ("C", "P"):
                mid = float(black_scholes.price(spot, k, t, R, 0.0, smile(k), right == "C"))
                rows.append(quote_row(uid, session, expiry, right, k, mid - 0.01, mid + 0.01))
    return rows


def run(rows, spots=None, params=P, close=True):
    spots = spots or {"EQ:A": 100.0}
    underlyings = pd.DataFrame(
        {
            "instrument_id": list(spots),
            "close": list(spots.values()) if close else np.nan,
            "price": list(spots.values()),
        }
    )
    inputs = {
        sk.OPTIONS: pd.DataFrame(rows),
        sk.RATES: pd.DataFrame({"tenor_days": [30, 365], "rate_cont": [R, R]}),
        sk.UNDERLYINGS: underlyings,
    }
    return sk.compute(inputs, END, params).set_index("instrument_id")


def strike_at_delta(smile, t, target, is_call, spot=100.0):
    """The strike whose delta at its own smile vol is ``target`` (bisection: |delta| falls as
    the strike moves away from the money, up for a call and down for a put)."""
    lo, hi = (spot, 160.0) if is_call else (40.0, spot)
    for _ in range(60):
        mid = (lo + hi) / 2
        delta = float(black_scholes.greeks(spot, mid, t, R, 0.0, smile(mid), is_call).delta)
        too_close = abs(delta) > abs(target)
        if too_close == is_call:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def test_the_worked_example_one_expiry_and_the_term_step() -> None:
    puts = (np.array([-0.30, -0.20]), np.array([0.31, 0.34]))
    calls = (np.array([0.20, 0.30]), np.array([0.26, 0.27]))
    atm_calls = (np.array([0.45, 0.55]), np.array([0.280, 0.285]))
    atm_puts = (np.array([-0.55, -0.45]), np.array([0.300, 0.290]))
    iv_25p = sk.vol_at_delta(*puts, -0.25)
    iv_25c = sk.vol_at_delta(*calls, 0.25)
    iv_atm = (sk.vol_at_delta(*atm_calls, 0.5) + sk.vol_at_delta(*atm_puts, -0.5)) / 2
    assert (iv_25p, iv_25c) == (pytest.approx(0.325), pytest.approx(0.265))
    assert iv_atm == pytest.approx(0.28875)
    assert (iv_25p - iv_25c) / iv_atm == pytest.approx(0.208, abs=5e-4)
    # the term step: 0.325 at 21 days and 0.315 at 49 days, to 30 days
    iv, status = term_vol((21 / 365, 0.325), (49 / 365, 0.315), 30 / 365)
    assert status == "OK" and iv == pytest.approx(0.3198, abs=5e-5)


def test_term_columns_interpolate_each_vol_then_form_the_skew() -> None:
    near, far = END + timedelta(days=21), END + timedelta(days=49)
    table = {
        ("EQ:A", near): {"iv_25p": 0.325, "iv_25c": 0.265, "iv_atm": 0.28875},
        ("EQ:A", far): {"iv_25p": 0.315, "iv_25c": 0.27, "iv_atm": 0.285},
    }
    picked = pd.DataFrame({"underlying_id": "EQ:A", "expiry": [near, far], "role": ["near", "far"]})
    out = sk.term_columns(picked, table, END, P)
    assert out["skew_status"] == "OK" and out["iv_25p"] == pytest.approx(0.3198, abs=5e-5)
    assert out["skew"] == pytest.approx((out["iv_25p"] - out["iv_25c"]) / out["iv_atm"])
    one = sk.term_columns(picked.iloc[:1], table, END, P)  # one expiry: its vols unchanged
    assert one["skew_status"] == "SINGLE_EXPIRY" and one["iv_25p"] == pytest.approx(0.325)
    assert one["skew"] == pytest.approx(0.2078, abs=5e-4)


def test_vol_at_delta_brackets_exactly_and_never_extrapolates() -> None:
    delta, iv = np.array([-0.40, -0.30, -0.20]), np.array([0.30, 0.32, 0.36])
    assert sk.vol_at_delta(delta, iv, -0.25) == pytest.approx(0.34)
    assert sk.vol_at_delta(delta, iv, -0.30) == pytest.approx(0.32)  # exactly on a contract
    assert np.isnan(sk.vol_at_delta(delta, iv, -0.10))  # beyond the quoted deltas
    assert np.isnan(sk.vol_at_delta(delta, iv, -0.50))
    assert np.isnan(sk.vol_at_delta(delta[:0], iv[:0], -0.25))


def test_a_flat_smile_has_no_skew_and_a_skewed_one_reads_its_25_delta_vols() -> None:
    flat = chain_rows("EQ:FLAT", END, 100.0, {NEAR: 0.30, FAR: 0.30}, R)
    smile = line(0.30, -0.004)  # higher vol at lower strikes: put-rich
    rows = [*flat, *smile_chain("EQ:A", [NEAR, FAR], smile)]
    out = run(rows, {"EQ:FLAT": 100.0, "EQ:A": 100.0})
    flat_row = out.loc["EQ:FLAT"]
    assert flat_row["skew_status"] == "OK"
    assert flat_row["skew"] == pytest.approx(0.0, abs=2e-4)
    assert flat_row["iv_25p"] == pytest.approx(0.30, abs=2e-4)
    a = out.loc["EQ:A"]
    assert a["skew_status"] == "OK" and a["iv_25p"] > a["iv_atm"] > a["iv_25c"]
    # independent read: the 25-delta strikes by bisection at each expiry, then the term step
    for column, right, target in (("iv_25p", False, -0.25), ("iv_25c", True, 0.25)):
        per_expiry = []
        for days in (14, 49):
            k = strike_at_delta(smile, days / 365, target, right)
            per_expiry.append((days / 365, smile(k)))
        iv, _ = term_vol(*per_expiry, 30 / 365)
        assert a[column] == pytest.approx(iv, abs=2e-3)  # linear in delta between $1 strikes
    assert a["skew"] == pytest.approx((a["iv_25p"] - a["iv_25c"]) / a["iv_atm"])


def test_a_listed_expiry_exactly_on_30_days_is_ok_not_single() -> None:
    on = END + timedelta(days=30)
    out = run(smile_chain("EQ:A", [on], line(0.30, -0.002)))
    assert out.loc["EQ:A", "skew_status"] == "OK"  # near == far: flat, both slots filled


def test_one_usable_expiry_is_single_expiry_with_its_values() -> None:
    out = run(smile_chain("EQ:A", [NEAR], line(0.30, -0.003)))  # nothing at or after 30 days
    a = out.loc["EQ:A"]
    assert a["skew_status"] == "SINGLE_EXPIRY" and a["skew"] > 0
    assert a["iv_atm"] == pytest.approx(0.30, abs=0.01)  # atm at the money: sigma(100)


def test_the_next_expiry_is_the_first_listed_with_no_interpolation() -> None:
    rows = smile_chain("EQ:A", [WEEKLY, NEAR, FAR], line(0.30, -0.003))
    a = run(rows).loc["EQ:A"]
    assert a["ne_dte"] == 3
    assert a["ne_skew"] > 0 and a["skew_status"] == "OK"
    only = run(smile_chain("EQ:B", [WEEKLY], line(0.30, -0.003)), {"EQ:B": 100.0}).loc["EQ:B"]
    assert only["skew_status"] == "NO_EXPIRY"  # 3 days out is under the 7-day floor
    assert only["ne_dte"] == 3 and only["ne_skew"] > 0  # the next-expiry columns still read it


def test_every_status() -> None:
    puts_only = [r for r in smile_chain("EQ:NOATM", [NEAR, FAR], line(0.3, 0)) if r["right"] == "P"]
    narrow = smile_chain("EQ:NOWING", [NEAR, FAR], line(0.3, 0), strikes=range(98, 103))
    wide = [
        quote_row("EQ:WIDE", END, e, r, k, 0.5, 2.0)  # spread 1.5 / 1.25 = 120% of mid
        for e in (NEAR, FAR)
        for r in "CP"
        for k in range(80, 125, 5)
    ]
    rows = [
        *smile_chain("EQ:OK", [NEAR, FAR], line(0.3, -0.002)),
        *smile_chain("EQ:ONE", [NEAR], line(0.3, -0.002)),
        *smile_chain("EQ:SHORT", [WEEKLY], line(0.3, 0)),
        *puts_only,
        *narrow,
        *wide,
        *smile_chain("EQ:NOSPOT", [NEAR, FAR], line(0.3, 0)),
    ]
    spots = dict.fromkeys(
        ("EQ:OK", "EQ:ONE", "EQ:SHORT", "EQ:NOATM", "EQ:NOWING", "EQ:WIDE", "EQ:NOCHAIN"), 100.0
    )
    spots["EQ:NOSPOT"] = np.nan
    out = run(rows, spots)
    status = out["skew_status"].to_dict()
    assert status == {
        "EQ:NOATM": "NO_ATM",  # puts only: no call vol at +0.50
        "EQ:NOCHAIN": "NO_CHAIN",
        "EQ:NOSPOT": "NO_SPOT",
        "EQ:NOWING": "NO_WING",  # strikes 98..102: the 25-delta strikes are outside them
        "EQ:OK": "OK",
        "EQ:ONE": "SINGLE_EXPIRY",
        "EQ:SHORT": "NO_EXPIRY",
        "EQ:WIDE": "NO_ATM",  # no smile quote survives the 35% spread cut
    }
    bad = out[~out["skew_status"].isin(["OK", "SINGLE_EXPIRY"])]
    assert bad[["skew", "iv_25p", "iv_25c", "iv_atm"]].isna().all().all()  # null is UNKNOWN
    assert out.loc["EQ:NOCHAIN", ["ne_skew", "ne_dte"]].isna().all()
    assert pd.isna(out.loc["EQ:NOSPOT", "ne_skew"])


def test_spot_is_the_close_then_the_price() -> None:
    rows = smile_chain("EQ:A", [NEAR, FAR], line(0.3, -0.002))
    by_close = run(rows).loc["EQ:A"]
    by_price = run(rows, close=False).loc["EQ:A"]  # close missing: the price (the same here)
    assert by_price["skew"] == pytest.approx(by_close["skew"])
    stale = pd.DataFrame(
        {"instrument_id": ["EQ:A"], "close": [100.0], "price": [130.0]}  # an after-hours price
    )
    inputs = {
        sk.OPTIONS: pd.DataFrame(rows),
        sk.RATES: pd.DataFrame({"tenor_days": [30], "rate_cont": [R]}),
        sk.UNDERLYINGS: stale,
    }
    out = sk.compute(inputs, END, P).set_index("instrument_id").loc["EQ:A"]
    assert out["skew"] == pytest.approx(by_close["skew"])  # the close, not the price


def test_params_share_iv30s_checks() -> None:
    with pytest.raises(ValueError, match="min_days"):
        replace(P, min_days=40)
    with pytest.raises(ValueError, match="max_spread_pct"):
        replace(P, max_spread_pct=0)


def test_a_session_reads_only_its_chain_partition() -> None:
    writer, reader = store()
    earlier, later = END - timedelta(days=1), END
    for day, slope in ((earlier, -0.001), (later, -0.006)):
        expiries = [day + timedelta(days=21), day + timedelta(days=49)]
        rows = smile_chain("EQ:A", expiries, line(0.30, slope), session=day)
        write_chains(writer, day, rows, {"EQ:A": 100.0})
        write_curve(writer, day, R)
    first = compute_one(reader, GROUP, earlier).frame
    second = compute_one(reader, GROUP, later).frame
    assert first is not None and second is not None
    assert first.iloc[0]["skew_status"] == "OK" and second.iloc[0]["skew_status"] == "OK"
    assert second.iloc[0]["skew"] > 3 * first.iloc[0]["skew"]  # each session its own smile
    assert GROUP.table == "rollups/instrument/skew@v1"
