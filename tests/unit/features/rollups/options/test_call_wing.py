"""``call_wing@v1`` on synthetic chains priced by ``quant.black_scholes`` at a known vol: the
covered-call mirror of ``put_wing@v1`` through the same search. The target expiry, OUR call
delta (the feed's is ignored), the 0.15..0.30 band with both edges included, the band
totals, the best call (nearest the band, then the premium yield mid / spot, then the higher
open interest, then the higher strike) and its band distance, every status with its nulls,
point in time through the runner, and properties on random chains."""

from dataclasses import replace
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from algotrade.features.framework.runner import compute_one
from algotrade.features.registry import GROUPS
from algotrade.features.rollups.options import call_wing as cw
from algotrade.features.rollups.options import wing_search as ws
from algotrade.quant.black_scholes import greeks
from tests.helpers.rollup_store import END, chain_rows, store, write_chains, write_curve

P = cw.CallWingParams()
E25, E45, E65 = (END + timedelta(days=d) for d in (25, 45, 65))
STRIKES = tuple(range(60, 161))
BEST = (
    "delta_band_distance", "best_call_strike", "best_call_delta", "best_call_iv",
    "best_call_mid", "best_call_oi", "best_call_volume", "best_call_spread_pct",
    "best_call_yield",
)  # fmt: skip


def run(
    options: list[dict[str, object]],
    spots: dict[str, float],
    rate: float = 0.04,
    params: cw.CallWingParams = P,
) -> pd.DataFrame:
    inputs = {
        cw.OPTIONS: pd.DataFrame(options),
        cw.RATES: pd.DataFrame({"tenor_days": [30, 365], "rate_cont": [rate, rate]}),
        cw.UNDERLYINGS: pd.DataFrame(
            {"instrument_id": list(spots), "price": list(spots.values()), "iv30": 30.0}
        ),
    }
    return cw.compute(inputs, END, params).set_index("instrument_id")


def expected_wing(spot: float, expiry, sigma: float, r: float) -> dict:
    """The qualifying strikes and their deltas / mids, straight from the model."""
    t = (expiry - END).days / 365
    k = np.array(STRIKES, dtype=float)
    g = greeks(spot, k, t, r, 0.0, sigma, True)
    band = (g.delta >= P.delta_lo) & (g.delta <= P.delta_hi)
    return {"strikes": k[band], "delta": g.delta[band], "mid": g.price[band]}


def test_our_call_delta_band_and_best_call_by_yield() -> None:
    rows = chain_rows("EQ:A", END, 100.0, {E25: 0.4, E45: 0.4, E65: 0.4}, 0.04, strikes=STRIKES)
    out = run(rows, {"EQ:A": 100.0}).loc["EQ:A"]
    want = expected_wing(100.0, E45, 0.4, 0.04)
    assert (out["wing_status"], out["target_expiry"], out["target_dte"]) == ("OK", E45, 45)
    assert out["n_strikes"] == len(want["strikes"]) >= 3
    assert out["wing_oi"] == 500 * len(want["strikes"])  # chain_rows: OI 500, volume 10 each
    assert out["wing_volume"] == 10 * len(want["strikes"])
    premium = want["mid"] / 100.0
    best = int(np.argmax(premium))
    assert best == 0  # a call's premium falls with the strike: the lowest strike in the band
    assert out["best_call_strike"] == want["strikes"][best]
    assert out["best_call_delta"] == pytest.approx(want["delta"][best], abs=1e-6)
    assert P.delta_lo <= out["best_call_delta"] <= P.delta_hi
    assert out["best_call_iv"] == pytest.approx(0.4, abs=1e-6)
    assert out["best_call_mid"] == pytest.approx(want["mid"][best], rel=1e-6)
    assert out["best_call_yield"] == pytest.approx(premium[best], rel=1e-6)
    assert (out["best_call_oi"], out["best_call_volume"]) == (500, 10)
    assert out["delta_band_distance"] == 0
    assert out["best_call_spread_pct"] == pytest.approx(0.02 / want["mid"][best], rel=1e-6)
    spreads = 0.02 / want["mid"]
    assert out["wing_spread_pct"] == pytest.approx(float(np.median(spreads)), rel=1e-6)


def test_the_yield_is_per_dollar_of_stock_not_per_strike() -> None:
    """The put ranks by mid / strike; the call by mid / the underlying's price."""
    rows = chain_rows("EQ:A", END, 80.0, {E45: 0.4}, 0.04, strikes=STRIKES)
    out = run(rows, {"EQ:A": 80.0}).loc["EQ:A"]
    assert out["best_call_yield"] == pytest.approx(out["best_call_mid"] / 80.0, rel=1e-6)
    assert out["best_call_yield"] != pytest.approx(out["best_call_mid"] / out["best_call_strike"])


def test_without_a_band_strike_the_nearest_candidate_wins_and_reports_its_distance() -> None:
    """Strikes 106 and 108 only: no 15-30 delta call (both above 0.30), so the best call is the
    one nearest the band (108), not the higher-premium 106 (further from it)."""
    rows = chain_rows("EQ:A", END, 100.0, {E45: 0.4}, 0.04, strikes=(106, 108))
    out = run(rows, {"EQ:A": 100.0}).loc["EQ:A"]
    size = greeks(100.0, np.array([106.0, 108.0]), 45 / 365, 0.04, 0.0, 0.4, True).delta
    assert P.delta_hi < size[1] < size[0] <= P.search_hi
    assert (out["wing_status"], out["best_call_strike"]) == ("OUTSIDE_BAND", 108.0)
    assert out["delta_band_distance"] == pytest.approx(size[1] - P.delta_hi, abs=1e-6)
    assert (out["n_strikes"], out["wing_oi"], out["wing_volume"]) == (0, 0, 0)
    assert pd.isna(out["wing_spread_pct"])


def test_the_feeds_delta_is_ignored() -> None:
    rows = chain_rows("EQ:A", END, 100.0, {E45: 0.4}, 0.04, strikes=STRIKES)
    assert {r["delta"] for r in rows} == {0.5}  # the feed's: every call would be a 50 delta
    out = run(rows, {"EQ:A": 100.0}).loc["EQ:A"]
    assert out["wing_status"] == "OK" and out["best_call_delta"] < 0.31


def _wing(deltas: list[float], **columns: list[float]) -> pd.DataFrame:
    n = len(deltas)
    return pd.DataFrame(
        {
            "strike": columns.get("strike", [110.0 + i for i in range(n)]),
            "bid": [1.0] * n,
            "ask": [1.1] * n,
            "mid": columns.get("mid", [1.05] * n),
            "iv": [0.4] * n,
            "delta": deltas,
            "open_interest": columns.get("oi", [100.0] * n),
            "volume": [5.0] * n,
            "spot": [100.0] * n,
        }
    )


@pytest.mark.parametrize(
    ("delta", "status", "distance"),
    [
        (0.15, "OK", 0.0),
        (0.30, "OK", 0.0),
        (0.225, "OK", 0.0),
        (0.1499999, "OUTSIDE_BAND", 1e-7),
        (0.3000001, "OUTSIDE_BAND", 1e-7),
        (0.05, "OUTSIDE_BAND", 0.10),  # the search range's edges are candidates
        (0.50, "OUTSIDE_BAND", 0.20),
        (0.0499999, "NO_STRIKE", None),
        (0.5000001, "NO_STRIKE", None),
        (float("nan"), "NO_STRIKE", None),
    ],
)
def test_delta_band_and_search_edges_are_included(
    delta: float, status: str, distance: float | None
) -> None:
    row = ws.wing_row(_wing([delta]), P, cw.SIDE)
    assert row["wing_status"] == status
    assert row["n_strikes"] == int(status == "OK")
    assert row["n_unpriced"] == int(np.isnan(delta))
    if distance is None:
        assert "delta_band_distance" not in row and "best_call_strike" not in row
    else:
        assert row["delta_band_distance"] == pytest.approx(distance, abs=1e-9)


def test_closeness_to_the_band_ranks_before_the_yield() -> None:
    """35 delta beats 45 delta whatever the premium; inside the band the highest yield wins."""
    out_of_band = _wing([0.45, 0.35], strike=[102.0, 106.0], mid=[5.0, 3.0])
    row = ws.wing_row(out_of_band, P, cw.SIDE)
    assert row["best_call_strike"] == 106.0
    assert row["delta_band_distance"] == pytest.approx(0.05)
    inside = _wing([0.16, 0.22, 0.28], strike=[125.0, 112.0, 106.0], mid=[0.5, 1.7, 2.9])
    best = ws.wing_row(inside, P, cw.SIDE)
    assert (best["best_call_strike"], best["delta_band_distance"]) == (106.0, 0.0)  # 2.9 / 100
    assert best["best_call_yield"] == pytest.approx(0.029)


def test_best_call_ties_higher_oi_then_higher_strike() -> None:
    tie = _wing([0.2, 0.2, 0.2], strike=[110.0, 120.0, 130.0], mid=[1.0, 1.0, 1.0], oi=[9, 9, 5])
    row = ws.wing_row(tie, P, cw.SIDE)  # equal yield; OI 9 beats 5; then the higher strike
    assert (row["best_call_strike"], row["best_call_oi"]) == (120.0, 9)
    nan_oi = _wing([0.2, 0.2], mid=[1.0, 1.0], oi=[float("nan"), 3.0])
    assert ws.wing_row(nan_oi, P, cw.SIDE)["wing_oi"] == 3  # unknown OI counts as none


def test_statuses_and_nulls() -> None:
    puts_only = [
        r for r in chain_rows("EQ:PUTS", END, 100.0, {E45: 0.4}, 0.04) if r["right"] == "P"
    ]
    rows = [
        *chain_rows("EQ:OK", END, 100.0, {E45: 0.4}, 0.04, strikes=STRIKES),
        *chain_rows("EQ:NOSPOT", END, 100.0, {E45: 0.4}, 0.04, strikes=STRIKES),
        *puts_only,
        *chain_rows("EQ:NEAR", END, 100.0, {E25: 0.4, E65: 0.4}, 0.04, strikes=STRIKES),
        *chain_rows("EQ:ATM", END, 100.0, {E45: 0.4}, 0.04, strikes=(95, 100)),  # delta > 0.50
        *chain_rows("EQ:ONESIDED", END, 100.0, {E45: 0.4}, 0.04, strikes=STRIKES, spread=500.0),
    ]
    spots = dict.fromkeys(("EQ:OK", "EQ:PUTS", "EQ:NEAR", "EQ:ATM", "EQ:ONESIDED"), 100.0)
    out = run(rows, {**spots, "EQ:NOSPOT": 0.0, "EQ:NOCHAIN": 50.0})
    assert out["wing_status"].to_dict() == {
        "EQ:ATM": "NO_STRIKE",
        "EQ:PUTS": "NO_CHAIN",  # puts are not covered-call candidates
        "EQ:NEAR": "NO_EXPIRY",
        "EQ:NOCHAIN": "NO_CHAIN",
        "EQ:NOSPOT": "NO_SPOT",
        "EQ:OK": "OK",
        "EQ:ONESIDED": "NO_STRIKE",
    }
    no_target = out.loc[["EQ:PUTS", "EQ:NEAR", "EQ:NOCHAIN", "EQ:NOSPOT"]]
    assert no_target.drop(columns="wing_status").isna().all().all()
    for iid in ("EQ:ATM", "EQ:ONESIDED"):
        row = out.loc[iid]
        assert row["target_expiry"] == E45 and row["n_strikes"] == row["wing_oi"] == 0
        assert row[[*BEST, "wing_spread_pct"]].isna().all()
    assert out.loc["EQ:ONESIDED", "n_unpriced"] == len(STRIKES)  # bid floored at 0
    assert out.loc["EQ:ATM", "n_unpriced"] == 0


def test_point_in_time_through_the_runner() -> None:
    writer, reader = store()
    later = END + timedelta(days=3)
    write_curve(writer, END, 0.04)
    write_chains(
        writer,
        END,
        chain_rows("EQ:A", END, 100.0, {E45: 0.4}, 0.04, strikes=STRIKES),
        {"EQ:A": 100.0},
    )
    moved = chain_rows("EQ:A", later, 60.0, {E45: 0.9}, 0.04, strikes=STRIKES)
    write_chains(writer, later, moved, {"EQ:A": 60.0})
    frame = compute_one(reader, cw.GROUP, END).frame
    assert frame is not None
    out = frame.set_index("instrument_id").loc["EQ:A"]
    assert out["target_dte"] == 45 and out["best_call_iv"] == pytest.approx(0.4, abs=1e-6)
    assert str(frame["best_call_yield"].dtype) == "float32"
    assert GROUPS["call_wing@v1"].table == "rollups/instrument/call_wing@v1"


def test_params_validate_and_are_the_covered_call_bands() -> None:
    assert (P.delta_lo, P.delta_hi, P.search_lo, P.search_hi) == (0.15, 0.30, 0.05, 0.50)
    assert (P.dte_min, P.dte_target, P.dte_max) == (30, 45, 60)
    with pytest.raises(ValueError, match="dte_min"):
        replace(P, dte_min=50)
    with pytest.raises(ValueError, match="delta_lo"):
        replace(P, delta_lo=0.4)
    with pytest.raises(ValueError, match="search_hi"):
        replace(P, search_hi=0.2)


@settings(max_examples=30, deadline=None)
@given(
    spot=st.floats(20, 500),
    sigma=st.floats(0.1, 1.5),
    rate=st.floats(0.0, 0.08),
    dte=st.integers(30, 60),
    seed=st.integers(0, 2**16),
)
def test_properties_on_random_chains(
    spot: float, sigma: float, rate: float, dte: int, seed: int
) -> None:
    """Band strikes are exactly those whose model delta is in the band; the best call is in
    the search range, nearest the band, with the highest yield among equally near calls; row
    order never matters."""
    expiry = END + timedelta(days=dte)
    strikes = tuple(np.round(np.linspace(spot * 0.8, spot * 2.0, 60), 2))
    rows = chain_rows("EQ:R", END, spot, {expiry: sigma}, rate, strikes=strikes, spread=0.0)
    rows = [{**r, "bid": r["bid"] - 1e-4, "ask": r["ask"] + 1e-4} for r in rows]  # two-sided
    rng = np.random.default_rng(seed)
    shuffled = [rows[i] for i in rng.permutation(len(rows))]
    out = run(rows, {"EQ:R": spot}, rate=rate).loc["EQ:R"]
    again = run(shuffled, {"EQ:R": spot}, rate=rate).loc["EQ:R"]
    pd.testing.assert_series_equal(out, again)
    k = np.array(strikes)
    g = greeks(spot, k, dte / 365, rate, 0.0, sigma, True)
    priced = g.price - 1e-4 > 0
    inside = priced & (g.delta >= P.delta_lo + 1e-6) & (g.delta <= P.delta_hi - 1e-6)
    maybe = priced & (g.delta >= P.delta_lo - 1e-6) & (g.delta <= P.delta_hi + 1e-6)
    assert int(inside.sum()) <= out["n_strikes"] <= int(maybe.sum())
    found = priced & (g.delta >= P.search_lo - 1e-6) & (g.delta <= P.search_hi + 1e-6)
    if out["wing_status"] in ("OK", "OUTSIDE_BAND"):
        assert P.search_lo - 1e-9 <= out["best_call_delta"] <= P.search_hi + 1e-9
        assert out["best_call_yield"] == pytest.approx(out["best_call_mid"] / spot, rel=1e-5)
        distance = ws.band_distance(pd.Series(g.delta[found]), P).to_numpy()
        assert out["delta_band_distance"] == pytest.approx(distance.min(), abs=1e-5)
        assert (out["wing_status"] == "OK") == (out["delta_band_distance"] == 0)
        if out["wing_status"] == "OK":
            best_yield = float(np.max((g.price / spot)[inside], initial=0))
            assert out["best_call_yield"] >= best_yield * (1 - 1e-5)
            assert out["best_call_oi"] <= out["wing_oi"]
            assert 0 <= out["wing_spread_pct"] <= 2
    else:
        assert out["wing_status"] == "NO_STRIKE" and not inside.any()
