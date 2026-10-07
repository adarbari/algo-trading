"""``put_wing@v1`` on synthetic chains priced by ``quant.black_scholes`` at a known vol: the
target expiry, OUR delta (the feed's is ignored), the |delta| band with both edges included,
the band totals, the best put (nearest the band, then cash-secured ROC) and its band
distance, every status with its nulls, point in time through the runner, and properties on
random chains."""

from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from algotrade.features.framework.runner import compute_one
from algotrade.features.registry import GROUPS
from algotrade.features.rollups.options import put_wing as pw
from algotrade.features.rollups.options import wing_search as ws
from algotrade.quant.black_scholes import greeks
from tests.helpers.rollup_store import END, chain_rows, store, write_chains, write_curve

P = pw.PutWingParams()
E25, E35, E45, E50, E65 = (END + timedelta(days=d) for d in (25, 35, 45, 50, 65))
STRIKES = tuple(range(50, 101))
BEST = (
    "delta_band_distance", "best_put_strike", "best_put_delta", "best_put_iv", "best_put_mid",
    "best_put_oi", "best_put_volume", "best_put_spread_pct", "best_put_roc",
)  # fmt: skip


def run(
    options: list[dict[str, object]],
    spots: dict[str, float],
    rate: float = 0.04,
    yields: dict[str, float] | None = None,
    params: pw.PutWingParams = P,
) -> pd.DataFrame:
    inputs = {
        pw.OPTIONS: pd.DataFrame(options),
        pw.RATES: pd.DataFrame({"tenor_days": [30, 365], "rate_cont": [rate, rate]}),
        pw.UNDERLYINGS: pd.DataFrame(
            {"instrument_id": list(spots), "price": list(spots.values()), "iv30": 30.0}
        ),
        pw.DIVIDENDS: pd.DataFrame(
            {
                "instrument_id": list(yields or {}),
                "session_date": [END] * len(yields or {}),
                "div_yield": list((yields or {}).values()),
            }
        ),
    }
    return pw.compute(inputs, END, params).set_index("instrument_id")


def expected_wing(spot: float, expiry: date, sigma: float, r: float, q: float = 0.0) -> dict:
    """The qualifying strikes and their deltas / mids, straight from the model."""
    t = (expiry - END).days / 365
    k = np.array(STRIKES, dtype=float)
    g = greeks(spot, k, t, r, q, sigma, False)
    band = (np.abs(g.delta) >= P.delta_lo) & (np.abs(g.delta) <= P.delta_hi)
    return {"strikes": k[band], "delta": g.delta[band], "mid": g.price[band]}


def test_our_delta_band_and_best_put_by_roc() -> None:
    rows = chain_rows("EQ:A", END, 100.0, {E35: 0.4, E45: 0.4, E65: 0.4}, 0.04, strikes=STRIKES)
    out = run(rows, {"EQ:A": 100.0}).loc["EQ:A"]
    want = expected_wing(100.0, E45, 0.4, 0.04)
    assert (out["wing_status"], out["target_expiry"], out["target_dte"]) == ("OK", E45, 45)
    assert out["n_strikes"] == len(want["strikes"]) >= 3
    assert out["wing_oi"] == 500 * len(want["strikes"])  # chain_rows: OI 500, volume 10 each
    assert out["wing_volume"] == 10 * len(want["strikes"])
    roc = want["mid"] / want["strikes"]
    best = int(np.argmax(roc))
    assert out["best_put_strike"] == want["strikes"][best]
    assert out["best_put_delta"] == pytest.approx(want["delta"][best], abs=1e-6)
    assert out["best_put_iv"] == pytest.approx(0.4, abs=1e-6)
    assert out["best_put_mid"] == pytest.approx(want["mid"][best], rel=1e-6)
    assert out["best_put_roc"] == pytest.approx(roc[best], rel=1e-6)
    assert (out["best_put_oi"], out["best_put_volume"]) == (500, 10)
    assert out["delta_band_distance"] == 0
    assert out["best_put_spread_pct"] == pytest.approx(0.02 / want["mid"][best], rel=1e-6)
    spreads = 0.02 / want["mid"]
    assert out["wing_spread_pct"] == pytest.approx(float(np.median(spreads)), rel=1e-6)


def test_without_a_band_strike_the_nearest_candidate_wins_and_reports_its_distance() -> None:
    """Strikes 90 and 92.5 only: no 8-15 delta put, so the best put is the candidate nearest
    the band (90, |delta| ~0.20), not the higher-ROC 92.5 (~0.25); band totals are 0."""
    rows = chain_rows("EQ:A", END, 100.0, {E45: 0.4}, 0.04, strikes=(90, 92.5))
    out = run(rows, {"EQ:A": 100.0}).loc["EQ:A"]
    g = greeks(100.0, np.array([90.0, 92.5]), 45 / 365, 0.04, 0.0, 0.4, False)
    size = np.abs(g.delta)
    assert P.delta_hi < size[0] < size[1] <= P.search_hi
    assert (out["wing_status"], out["best_put_strike"]) == ("OUTSIDE_BAND", 90.0)
    assert out["delta_band_distance"] == pytest.approx(size[0] - P.delta_hi, abs=1e-6)
    assert (out["n_strikes"], out["wing_oi"], out["wing_volume"]) == (0, 0, 0)
    assert pd.isna(out["wing_spread_pct"])


def test_the_feeds_delta_is_ignored_and_dividends_move_ours() -> None:
    rows = chain_rows("EQ:A", END, 100.0, {E45: 0.4}, 0.04, strikes=STRIKES)
    assert {r["delta"] for r in rows} == {0.5}  # the feed's: nothing would qualify
    plain = run(rows, {"EQ:A": 100.0}).loc["EQ:A"]
    assert plain["wing_status"] == "OK"
    paying = chain_rows("EQ:A", END, 100.0, {E45: 0.4}, 0.04, q=0.05, strikes=STRIKES)
    out = run(paying, {"EQ:A": 100.0}, yields={"EQ:A": 0.05}).loc["EQ:A"]
    want = expected_wing(100.0, E45, 0.4, 0.04, q=0.05)
    assert out["n_strikes"] == len(want["strikes"])
    assert out["best_put_iv"] == pytest.approx(0.4, abs=1e-6)


def test_target_expiry_closest_to_45_ties_to_the_earlier() -> None:
    puts = pd.DataFrame(
        {
            "underlying_id": ["A"] * 4 + ["B"] * 2 + ["C"] * 2,
            "expiry": [E25, E35, E50, E65, END + timedelta(days=40), E50, E25, E65],
        }
    )
    puts["dte"] = [(e - END).days for e in puts["expiry"]]
    targets = ws.target_expiries(puts, P).to_dict()
    assert targets == {"A": E50, "B": END + timedelta(days=40)}  # 40 and 50: the earlier
    edges = puts.assign(dte=[30, 60, 61, 29, 30, 60, 29, 61])
    assert ws.target_expiries(edges, P).to_dict() == {"A": E25, "B": END + timedelta(days=40)}


def test_standard_monthly_first_unless_disabled() -> None:
    weekly, monthly = END + timedelta(days=42), date(2026, 11, 20)  # 42 and 49 days out
    puts = pd.DataFrame({"underlying_id": ["A", "A"], "expiry": [weekly, monthly]})
    puts["dte"] = [(e - END).days for e in puts["expiry"]]
    assert ws.target_expiries(puts, P).to_dict() == {"A": monthly}
    assert ws.target_expiries(puts, replace(P, prefer_monthly=False)).to_dict() == {"A": weekly}
    outside = puts.assign(dte=[42, 61])  # a monthly outside the window never wins
    assert ws.target_expiries(outside, P).to_dict() == {"A": weekly}


def _wing(deltas: list[float], **columns: list[float]) -> pd.DataFrame:
    n = len(deltas)
    frame = pd.DataFrame(
        {
            "strike": columns.get("strike", [90.0 - i for i in range(n)]),
            "bid": [1.0] * n,
            "ask": [1.1] * n,
            "mid": columns.get("mid", [1.05] * n),
            "iv": [0.4] * n,
            "delta": deltas,
            "open_interest": columns.get("oi", [100.0] * n),
            "volume": [5.0] * n,
        }
    )
    return frame


@pytest.mark.parametrize(
    ("delta", "status", "distance"),
    [
        (-0.08, "OK", 0.0),
        (-0.15, "OK", 0.0),
        (-0.115, "OK", 0.0),
        (-0.0799999, "OUTSIDE_BAND", 1e-7),
        (-0.1500001, "OUTSIDE_BAND", 1e-7),
        (-0.05, "OUTSIDE_BAND", 0.03),  # the search range's edges are candidates
        (-0.35, "OUTSIDE_BAND", 0.20),
        (-0.0499999, "NO_STRIKE", None),
        (-0.3500001, "NO_STRIKE", None),
        (float("nan"), "NO_STRIKE", None),
    ],
)
def test_delta_band_and_search_edges_are_included(
    delta: float, status: str, distance: float | None
) -> None:
    row = ws.wing_row(_wing([delta]), P, pw.SIDE)
    assert row["wing_status"] == status
    assert row["n_strikes"] == int(status == "OK")
    assert row["n_unpriced"] == int(np.isnan(delta))
    if distance is None:
        assert "delta_band_distance" not in row and "best_put_strike" not in row
    else:
        assert row["delta_band_distance"] == pytest.approx(distance, abs=1e-9)


def test_closeness_to_the_band_ranks_before_roc() -> None:
    """20 delta beats 25 delta whatever the ROC; inside the band the highest ROC wins."""
    out_of_band = _wing([-0.25, -0.20], strike=[95.0, 90.0], mid=[3.0, 1.0])
    assert ws.wing_row(out_of_band, P, pw.SIDE)["best_put_strike"] == 90.0
    assert ws.wing_row(out_of_band, P, pw.SIDE)["delta_band_distance"] == pytest.approx(0.05)
    inside = _wing([-0.09, -0.14, -0.30], strike=[80.0, 85.0, 95.0], mid=[0.8, 1.7, 9.0])
    row = ws.wing_row(inside, P, pw.SIDE)
    assert (row["best_put_strike"], row["delta_band_distance"]) == (85.0, 0.0)  # 2% > 1%
    assert ws.band_distance(pd.Series([0.04, 0.08, 0.2]), P).round(9).tolist() == [
        0.04,
        0.0,
        0.05,
    ]


def test_best_put_ties_higher_oi_then_lower_strike() -> None:
    tie = _wing([-0.1, -0.1, -0.1], strike=[90.0, 80.0, 70.0], mid=[0.9, 0.8, 0.7], oi=[5, 9, 9])
    assert ws.wing_row(tie, P, pw.SIDE)["best_put_strike"] == 70.0  # equal ROC 1%; OI 9 beats 5
    assert ws.wing_row(tie, P, pw.SIDE)["best_put_oi"] == 9
    nan_oi = _wing([-0.1, -0.1], mid=[1.0, 1.0], oi=[float("nan"), 3.0])
    assert ws.wing_row(nan_oi, P, pw.SIDE)["wing_oi"] == 3  # unknown OI counts as none


def test_statuses_and_nulls() -> None:
    calls_only = [
        r for r in chain_rows("EQ:CALLS", END, 100.0, {E45: 0.4}, 0.04) if r["right"] == "C"
    ]
    rows = [
        *chain_rows("EQ:OK", END, 100.0, {E45: 0.4}, 0.04, strikes=STRIKES),
        *chain_rows("EQ:NOSPOT", END, 100.0, {E45: 0.4}, 0.04, strikes=STRIKES),
        *calls_only,
        *chain_rows("EQ:NEAR", END, 100.0, {E25: 0.4, E65: 0.4}, 0.04, strikes=STRIKES),
        *chain_rows("EQ:ATM", END, 100.0, {E45: 0.4}, 0.04, strikes=(100, 105)),  # |delta| > 0.35
        *chain_rows("EQ:ONESIDED", END, 100.0, {E45: 0.4}, 0.04, strikes=STRIKES, spread=50.0),
    ]
    spots = dict.fromkeys(("EQ:OK", "EQ:CALLS", "EQ:NEAR", "EQ:ATM", "EQ:ONESIDED"), 100.0)
    out = run(rows, {**spots, "EQ:NOSPOT": 0.0, "EQ:NOCHAIN": 50.0})
    assert out["wing_status"].to_dict() == {
        "EQ:ATM": "NO_STRIKE",
        "EQ:CALLS": "NO_CHAIN",
        "EQ:NEAR": "NO_EXPIRY",
        "EQ:NOCHAIN": "NO_CHAIN",
        "EQ:NOSPOT": "NO_SPOT",
        "EQ:OK": "OK",
        "EQ:ONESIDED": "NO_STRIKE",
    }
    no_target = out.loc[["EQ:CALLS", "EQ:NEAR", "EQ:NOCHAIN", "EQ:NOSPOT"]]
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
    frame = compute_one(reader, pw.GROUP, END).frame
    assert frame is not None
    out = frame.set_index("instrument_id").loc["EQ:A"]
    assert out["target_dte"] == 45 and out["best_put_iv"] == pytest.approx(0.4, abs=1e-6)
    assert str(frame["best_put_roc"].dtype) == "float32"
    assert GROUPS["put_wing@v1"].table == "rollups/instrument/put_wing@v1"


def test_params_validate() -> None:
    with pytest.raises(ValueError, match="dte_min"):
        replace(P, dte_min=50)
    with pytest.raises(ValueError, match="delta_lo"):
        replace(P, delta_lo=0.2)
    with pytest.raises(ValueError, match="search_hi"):
        replace(P, search_hi=0.1)
    narrow = run(
        chain_rows("EQ:A", END, 100.0, {E45: 0.4}, 0.04, strikes=STRIKES),
        {"EQ:A": 100.0},
        params=replace(P, delta_lo=0.10, delta_hi=0.10),
    )
    assert narrow.loc["EQ:A", "n_strikes"] == 0  # no strike lands exactly on 0.10


@settings(max_examples=40, deadline=None)
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
    """Band strikes are exactly those whose model delta is in the band; the best put is in
    the search range, nearest the band, with the highest ROC among equally near puts; row
    order never matters."""
    expiry = END + timedelta(days=dte)
    strikes = tuple(np.round(np.linspace(spot * 0.3, spot, 60), 2))
    rows = chain_rows("EQ:R", END, spot, {expiry: sigma}, rate, strikes=strikes, spread=0.0)
    rows = [{**r, "bid": r["bid"] - 1e-4, "ask": r["ask"] + 1e-4} for r in rows]  # two-sided
    rng = np.random.default_rng(seed)
    shuffled = [rows[i] for i in rng.permutation(len(rows))]
    out = run(rows, {"EQ:R": spot}, rate=rate).loc["EQ:R"]
    again = run(shuffled, {"EQ:R": spot}, rate=rate).loc["EQ:R"]
    pd.testing.assert_series_equal(out, again)
    t = dte / 365
    k = np.array(strikes)
    g = greeks(spot, k, t, rate, 0.0, sigma, False)
    priced = g.price - 1e-4 > 0  # a mid too small to bracket has no IV
    size = np.abs(g.delta)
    inside = priced & (size >= P.delta_lo + 1e-6) & (size <= P.delta_hi - 1e-6)
    maybe = priced & (size >= P.delta_lo - 1e-6) & (size <= P.delta_hi + 1e-6)
    assert int(inside.sum()) <= out["n_strikes"] <= int(maybe.sum())
    found = priced & (size >= P.search_lo - 1e-6) & (size <= P.search_hi + 1e-6)
    if out["wing_status"] in ("OK", "OUTSIDE_BAND"):
        assert P.search_lo - 1e-9 <= -out["best_put_delta"] <= P.search_hi + 1e-9
        assert out["best_put_roc"] == pytest.approx(
            out["best_put_mid"] / out["best_put_strike"], rel=1e-6
        )
        distance = ws.band_distance(pd.Series(size[found]), P).to_numpy()
        assert out["delta_band_distance"] == pytest.approx(distance.min(), abs=1e-5)
        assert (out["wing_status"] == "OK") == (out["delta_band_distance"] == 0)
        if out["wing_status"] == "OK":
            best_roc = float(np.max((g.price / k)[inside], initial=0))
            assert out["best_put_roc"] >= best_roc * (1 - 1e-5)
            assert out["best_put_oi"] <= out["wing_oi"]
            assert 0 <= out["wing_spread_pct"] <= 2
    else:
        assert out["wing_status"] == "NO_STRIKE" and not inside.any()
