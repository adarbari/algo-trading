"""The chain P&L arithmetic on synthetic chains priced by Black-Scholes at a known vol (mid =
the model price, a half-spread either side): a long ATM straddle's mid and executable P&L, the
daily delta hedge against an independent computation from the model's own delta, a put chosen
by its delta, the intrinsic exit at expiry, and a name UNMEASURED (a reason, no P&L, never a
zero) when a session's chain is stale or missing, a contract is not quoted at the exit, or no
expiry can be held to the window's end."""

from datetime import UTC, date, datetime

import numpy as np
import pandas as pd
import pytest

from algotrade.quant.black_scholes import greeks, price
from algotrade_ingestion.tasks.derived.option_paths import (
    ATM_STRADDLE,
    DayChain,
    structure_of,
    structure_rows,
)

DAYS = (date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7))
EXPIRY = date(2026, 11, 6)
VOL, HALF = 0.30, 0.05
SPOTS = (100.0, 102.0, 99.0)
A = "EQ:A"


def _quotes(
    day: date, spot: float, expiry: date = EXPIRY, skip: set[str] | None = None
) -> pd.DataFrame:
    t = (expiry - day).days / 365
    rows = []
    for strike in (90.0, 95.0, 100.0, 105.0, 110.0):
        for right in ("C", "P"):
            cid = f"{right}{int(strike)}"
            if cid in (skip or set()):
                continue
            mid = float(price(spot, strike, t, 0.0, 0.0, VOL, right == "C"))
            rows.append({"instrument_id": f"OPT:{cid}", "underlying_id": A, "expiry": expiry,
                         "right": right, "strike": strike, "bid": mid - HALF,
                         "ask": mid + HALF})  # fmt: skip
    return pd.DataFrame(rows)


def _chain(i: int, label: str | None = "OK", **kw: object) -> DayChain:
    labels = {} if label is None else {A: label}
    spots = {} if label is None else {A: SPOTS[i]}
    return DayChain(
        DAYS[i], _quotes(DAYS[i], SPOTS[i], **kw) if label else None, spots, labels,
        datetime(2026, 10, 5 + i, 23, tzinfo=UTC),
    )  # fmt: skip


def _window(**changes: DayChain) -> list[DayChain]:
    days = [_chain(i) for i in range(3)]
    for key, chain in changes.items():
        days[int(key.removeprefix("d"))] = chain
    return days


def rows_of(
    days: list[DayChain], structure: str, tenor: int, horizon: int = 2
) -> tuple[pd.DataFrame, datetime | None]:
    """``structure_rows`` over hand-built ``days`` (the loader serves them, whatever ids)."""
    by_day = {c.day: c for c in days}
    return structure_rows(
        [c.day for c in days], lambda d, ids: by_day[d], structure, tenor, horizon
    )


def _mid(day: int, cid: str, expiry: date = EXPIRY) -> float:
    strike, right = float(cid[1:]), cid[0]
    return float(
        price(SPOTS[day], strike, (expiry - DAYS[day]).days / 365, 0.0, 0.0, VOL, right == "C")
    )


def test_long_straddle_pnl_is_quoted_mid_and_executable() -> None:
    rows, known = rows_of(_window(), ATM_STRADDLE, 30)
    r = rows.iloc[0]
    assert (r["outcome_status"], r["call_id"], r["put_id"], r["strike"]) == (
        "COMPLETE", "OPT:C100", "OPT:P100", 100.0,
    )  # fmt: skip
    entry = _mid(0, "C100") + _mid(0, "P100")
    exit_ = _mid(2, "C100") + _mid(2, "P100")
    assert r["entry_mid"] == pytest.approx(entry)
    assert r["entry_ask"] == pytest.approx(entry + 2 * HALF)
    assert r["pnl_per_premium"] == pytest.approx((exit_ - entry) / entry)
    assert r["pnl_per_underlying"] == pytest.approx((exit_ - entry) / 100.0)
    assert r["pnl_exec_per_premium"] == pytest.approx(
        (exit_ - 2 * HALF - entry - 2 * HALF) / (entry + 2 * HALF)
    )
    assert r["exit_kind"] == "QUOTE"
    assert known == datetime(2026, 10, 7, 23, tzinfo=UTC)  # the exit's chain, never the write time


def test_hedged_pnl_matches_the_models_own_delta() -> None:
    r = rows_of(_window(), ATM_STRADDLE, 30)[0].iloc[0]
    gain = 0.0
    for k in (0, 1):
        t = (EXPIRY - DAYS[k]).days / 365
        delta = sum(
            float(greeks(SPOTS[k], 100.0, t, 0.0, 0.0, VOL, is_call).delta)
            for is_call in (True, False)
        )
        gain += delta * (SPOTS[k + 1] - SPOTS[k])
    entry = _mid(0, "C100") + _mid(0, "P100")
    exit_ = _mid(2, "C100") + _mid(2, "P100")
    assert r["hedged_pnl_per_underlying"] == pytest.approx((exit_ - entry - gain) / 100.0, abs=1e-6)
    assert r["hedged_pnl_per_premium"] == pytest.approx((exit_ - entry - gain) / entry, abs=1e-6)


def test_put_is_chosen_by_its_own_delta() -> None:
    rows, _ = rows_of(_window(), "put_delta_25", 30)
    r = rows.iloc[0]
    t = (EXPIRY - DAYS[0]).days / 365
    deltas = {
        s: abs(float(greeks(100.0, s, t, 0.0, 0.0, VOL, False).delta))
        for s in (90, 95, 100, 105, 110)
    }
    best = min(deltas, key=lambda s: abs(deltas[s] - 0.25))
    assert r["put_id"] == f"OPT:P{best}" and pd.isna(r["call_id"])
    exit_ = _mid(2, f"P{best}")
    entry = _mid(0, f"P{best}")
    assert r["pnl_per_premium"] == pytest.approx((exit_ - entry) / entry)


def test_exit_at_expiry_is_intrinsic() -> None:
    expiry = DAYS[2]
    days = [
        DayChain(c.day, _quotes(c.day, SPOTS[i], expiry), c.spots, c.labels, c.known)
        for i, c in enumerate(_window())
    ]
    r = rows_of(days, ATM_STRADDLE, 1)[0].iloc[0]
    assert r["exit_kind"] == "INTRINSIC"
    assert r["exit_mid"] == r["exit_bid"] == pytest.approx(1.0)  # |99 - 100| at the strike
    assert r["outcome_status"] == "COMPLETE"


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"d1": _chain(1, "STALE_DATA")}, "STALE_CHAIN:2026-10-06"),
        ({"d1": _chain(1, None)}, "NO_CHAIN:2026-10-06"),
        ({"d2": _chain(2, "STALE_DATA")}, "STALE_CHAIN:2026-10-07"),
        ({"d2": _chain(2, skip={"C100"})}, "NO_EXIT_QUOTE"),
        ({"d1": _chain(1, skip={"P100"})}, "NO_DELTA:2026-10-06"),
    ],
)
def test_unmeasured_names_carry_a_reason_and_no_pnl(
    changes: dict[str, DayChain], reason: str
) -> None:
    r = rows_of(_window(**changes), ATM_STRADDLE, 30)[0].iloc[0]
    assert r["outcome_status"] == "UNMEASURED" and r["outcome_reason"] == reason
    for column in ("pnl_per_premium", "pnl_exec_per_premium", "hedged_pnl_per_premium", "exit_mid"):
        assert pd.isna(r[column])  # never a zero, never a stale chain in its place


def test_a_zero_bid_entry_and_a_missing_expiry_are_reasons() -> None:
    thin = _chain(0)
    options = thin.options.assign(bid=0.0)
    rows, _ = rows_of(
        _window(d0=DayChain(thin.day, options, thin.spots, thin.labels, thin.known)),
        ATM_STRADDLE,
        30,
    )
    assert rows.iloc[0]["outcome_reason"] == "NO_ENTRY_QUOTE"
    far, _ = rows_of(_window(), ATM_STRADDLE, 90)  # no expiry 90 days out
    assert far.iloc[0]["outcome_reason"] == "NO_EXPIRY"


def test_only_names_with_an_ok_chain_at_the_entry_have_a_row() -> None:
    days = _window(d0=_chain(0, "STALE_DATA"))
    rows, _ = rows_of(days, ATM_STRADDLE, 30)
    assert rows.empty  # no entry chain, no position was ever knowable


def test_structure_keys() -> None:
    assert structure_of("put_delta_25").delta == pytest.approx(0.25)
    with pytest.raises(ValueError, match="unknown chain structure"):
        structure_of("iron_condor")
    assert np.isfinite(structure_of(ATM_STRADDLE).call)
