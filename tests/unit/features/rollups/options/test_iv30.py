"""``iv30@v1`` on synthetic chains priced by ``quant.black_scholes`` with known vols: sigma
is recovered, the term structure interpolates in total variance, calls and puts are averaged,
the forward picks the strikes, and every quality failure has its status."""

import math
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import date, timedelta

import pandas as pd
import pytest

from algotrade.features.framework.runner import compute_in_memory, compute_one
from algotrade.features.rollups.options import iv30, oi_walls, put_wing
from algotrade.features.rollups.options.iv30 import GROUP, Iv30Params, choose_expiries
from algotrade.quant.implied_vol import interpolate_total_variance
from tests.helpers.rollup_store import END, chain_rows, store, write_chains, write_curve

NEAR, FAR = date(2026, 10, 16), date(2026, 11, 20)  # 14 and 49 days; 11-20 is a monthly
T = (14 / 365, 49 / 365)


def run(
    options: Sequence[Mapping[str, object]],
    spots: Mapping[str, float],
    rate: float = 0.04,
    yields: Mapping[str, float] | None = None,
    params: Iv30Params | None = None,
) -> pd.DataFrame:
    inputs = {
        iv30.OPTIONS: pd.DataFrame(list(options)),
        iv30.RATES: pd.DataFrame({"tenor_days": [30, 365], "rate_cont": [rate, rate]}),
        iv30.UNDERLYINGS: pd.DataFrame(
            {
                "instrument_id": list(spots),
                "price": list(spots.values()),
                "iv30": [31.0] * len(spots),
            }
        ),
        iv30.DIVIDENDS: pd.DataFrame(
            {
                "instrument_id": list(yields or {}),
                "session_date": [END] * len(yields or {}),
                "div_yield": list((yields or {}).values()),
            }
        ),
    }
    return iv30.compute(inputs, END, params or Iv30Params()).set_index("instrument_id")


def test_recovers_a_flat_vol_with_rates_and_dividends() -> None:
    rows = chain_rows("EQ:A", END, 100.0, {NEAR: 0.30, FAR: 0.30}, 0.04, q=0.02)
    out = run(rows, {"EQ:A": 100.0}, yields={"EQ:A": 0.02}).loc["EQ:A"]
    assert out["iv30"] == pytest.approx(0.30, abs=1e-6)
    assert (out["iv30_status"], out["near_expiry"], out["far_expiry"]) == ("OK", NEAR, FAR)
    assert out["iv30_cboe"] == pytest.approx(0.31) and out["div_yield"] == 0.02
    assert (out["spot"], out["rate"], out["n_quotes_used"]) == (100.0, 0.04, 8)
    assert out["atm_strike_near"] == 100.0  # F = 100.08: 100 is nearest


def test_term_structure_is_linear_in_total_variance() -> None:
    rows = chain_rows("EQ:A", END, 100.0, {NEAR: 0.20, FAR: 0.40}, 0.04)
    got = run(rows, {"EQ:A": 100.0}).loc["EQ:A", "iv30"]
    w1, w2 = 0.2**2 * T[0], 0.4**2 * T[1]
    t30 = 30 / 365
    expected = math.sqrt((w1 + (w2 - w1) * (t30 - T[0]) / (T[1] - T[0])) / t30)
    assert got == pytest.approx(expected, abs=1e-6)
    assert float(interpolate_total_variance(T[0], 0.2, T[1], 0.4, t30)) == pytest.approx(expected)
    assert float(interpolate_total_variance(T[0], 0.25, T[0], 0.9, t30)) == 0.25  # one expiry
    assert math.isnan(float(interpolate_total_variance(0.1, 0.5, 0.2, 0.1, 1.0)))  # w < 0


def test_calls_and_puts_are_averaged_and_strikes_interpolated_to_the_forward() -> None:
    calls = [r for r in chain_rows("EQ:A", END, 100.0, {FAR: 0.28}, 0.04) if r["right"] == "C"]
    puts = [r for r in chain_rows("EQ:A", END, 100.0, {FAR: 0.32}, 0.04) if r["right"] == "P"]
    out = run(calls + puts, {"EQ:A": 100.0}).loc["EQ:A"]
    assert out["iv30"] == pytest.approx(0.30, abs=1e-6)
    assert out["iv30_status"] == "SINGLE_EXPIRY" and pd.isna(out["near_expiry"])
    # A smile: 100 at 30%, 105 at 40%; F = S = 102 (r = q) is 2/5 of the way: 34%.
    low = chain_rows("EQ:B", END, 102.0, {FAR: 0.30}, 0.03, 0.03, strikes=(100,))
    high = chain_rows("EQ:B", END, 102.0, {FAR: 0.40}, 0.03, 0.03, strikes=(105,))
    smile = run(low + high, {"EQ:B": 102.0}, rate=0.03, yields={"EQ:B": 0.03}).loc["EQ:B"]
    assert smile["iv30"] == pytest.approx(0.34, abs=1e-6)
    assert smile["atm_strike_near"] == 100.0


def _priced(uid: str, **changes: object) -> list[dict[str, object]]:
    return [{**r, **changes} for r in chain_rows(uid, END, 100.0, {NEAR: 0.3, FAR: 0.3}, 0.04)]


def test_quality_filters_and_status_codes() -> None:
    wide = chain_rows("EQ:WIDE", END, 100.0, {NEAR: 0.3, FAR: 0.3}, 0.04, spread=3.0)
    far_only = chain_rows("EQ:HALF", END, 100.0, {FAR: 0.3}, 0.04)
    near_wide = chain_rows("EQ:HALF", END, 100.0, {NEAR: 0.3}, 0.04, spread=3.0)
    rows = [
        *_priced("EQ:NOBID", bid=0.0),
        *wide,
        *_priced("EQ:THIN", open_interest=0.0, volume=0.0),
        *_priced("EQ:CHEAP", bid=99.0, ask=99.5),  # dearer than any vol up to 500%
        *_priced("EQ:NOSPOT"),
        *chain_rows("EQ:FARAWAY", END, 100.0, {END + timedelta(days=3): 0.3}, 0.04),
        *far_only,
        *near_wide,
    ]
    spots = dict.fromkeys(("EQ:NOBID", "EQ:WIDE", "EQ:THIN", "EQ:CHEAP", "EQ:FARAWAY"), 100.0)
    out = run(rows, {**spots, "EQ:HALF": 100.0, "EQ:NOSPOT": 0.0, "EQ:NOCHAIN": 50.0})
    status = out["iv30_status"].to_dict()
    assert status == {
        "EQ:CHEAP": "IV_FAILED",
        "EQ:FARAWAY": "NO_EXPIRY",
        "EQ:HALF": "SINGLE_EXPIRY",
        "EQ:NOBID": "NO_QUOTES",
        "EQ:NOCHAIN": "NO_CHAIN",
        "EQ:NOSPOT": "NO_SPOT",
        "EQ:THIN": "ILLIQUID",
        "EQ:WIDE": "WIDE_SPREADS",
    }
    assert out.loc["EQ:HALF", "iv30"] == pytest.approx(0.30, abs=1e-6)
    assert out.loc["EQ:HALF", "n_quotes_used"] == 4
    failed = out.drop(index="EQ:HALF")
    assert failed["iv30"].isna().all() and (failed["n_quotes_used"] == 0).all()
    loose = run(wide, {"EQ:WIDE": 100.0}, params=Iv30Params(max_spread_pct=5.0))
    assert loose.loc["EQ:WIDE", "iv30_status"] == "OK"


def test_expiry_choice() -> None:
    p = Iv30Params()
    weekly, monthly, later = date(2026, 10, 30), date(2026, 11, 20), date(2026, 12, 18)
    standard = {date(2026, 10, 16), monthly, later}
    listed = [date(2026, 10, 16), weekly, monthly, later]
    assert choose_expiries(listed, END, p, standard) == (date(2026, 10, 16), monthly)
    assert choose_expiries([weekly, monthly], END, p, set()) == (weekly, monthly)
    assert choose_expiries([monthly, later], END, p, standard) == (None, monthly)
    assert choose_expiries([date(2026, 10, 9)], END, p, set()) == (date(2026, 10, 9), None)
    on_target = END + timedelta(days=30)
    assert choose_expiries([on_target], END, p, set()) == (on_target, on_target)
    assert choose_expiries([END + timedelta(days=200)], END, p, set()) == (None, None)
    with pytest.raises(ValueError, match="min_days"):
        replace(p, min_days=40)
    with pytest.raises(ValueError, match="max_spread_pct"):
        replace(p, max_spread_pct=0.0)


def test_through_the_framework_with_stored_inputs() -> None:
    writer, reader = store()
    rows = chain_rows("EQ:A", END, 100.0, {NEAR: 0.25, FAR: 0.25}, 0.05)
    write_chains(writer, END, rows, {"EQ:A": 100.0})
    assert compute_one(reader, GROUP, END).no_input == f"no rates/treasury for {END}"
    write_curve(writer, END, 0.05)
    out = compute_in_memory(reader, [GROUP], [END])[GROUP.key][0].frame
    assert out is not None and out["iv30"].iloc[0] == pytest.approx(0.25, abs=1e-6)
    assert pd.isna(out["div_yield"].iloc[0])  # no div_yield@v1 stored: q = 0


def test_a_duplicated_underlying_keeps_its_latest_quote_whatever_the_row_order() -> None:
    older, newer = (
        pd.Timestamp("2026-10-02 15:00", tz="UTC"),
        pd.Timestamp("2026-10-02 20:00", tz="UTC"),
    )
    rows = [("EQ:A", newer, 12.0), ("EQ:A", older, 11.0), ("EQ:B", older, 5.0)]
    for order in (rows, rows[::-1]):
        quotes = pd.DataFrame(order, columns=["instrument_id", "ts", "price"])
        assert iv30.positive_spots(quotes).to_dict() == {"EQ:A": 12.0, "EQ:B": 5.0}


def test_spot_prices_are_the_one_spot_reader_of_the_chain_groups() -> None:
    quotes = pd.DataFrame(
        {
            "instrument_id": ["EQ:A", "EQ:B", "EQ:C", "EQ:D", "EQ:A"],
            "price": [10.0, 0.0, -1.0, None, 12.0],  # EQ:A quoted twice: the last row wins
            "iv30": 30.0,
        }
    )
    spots = iv30.spot_prices(quotes)
    assert list(spots.index) == ["EQ:B", "EQ:C", "EQ:D", "EQ:A"]
    assert spots["EQ:A"] == 12.0 and spots[["EQ:B", "EQ:C", "EQ:D"]].isna().all()
    assert iv30.positive_spots(quotes).to_dict() == {"EQ:A": 12.0}
    assert iv30.spot_prices(None).empty and iv30.positive_spots(quotes.iloc[:0]).empty
    assert put_wing.positive_spots is iv30.positive_spots
    assert oi_walls.positive_spots is iv30.positive_spots
