"""The option-structure engine (ADR 0088, design 2.4) on synthetic chains priced by Black-Scholes
at a known vol: a two-leg position's mid and executable value at entry and exit (a short leg is
sold at the bid and bought back at the ask), expiry at intrinsic, the daily hedge's net delta
against an independent computation, the exit fallback for a zero bid, and a name UNMEASURED with
a reason when its chain left (a delisting) or went stale, never filled from an earlier session."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from algotrade.data.chains import OK_LABEL, STALE
from algotrade.engines.structures.chain import DayChain, Labels
from algotrade.engines.structures.marking import LegColumn, Window, mark_window
from algotrade.quant.black_scholes import greeks, price

DAYS = (date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7))
EXPIRY = date(2026, 11, 6)
VOL, HALF = 0.30, 0.05
SPOTS = (100.0, 102.0, 99.0)
A = "EQ:A"


def quotes(day: int, expiry: date = EXPIRY, zero_bid: set[str] | None = None) -> pd.DataFrame:
    rows = []
    for strike in (90.0, 95.0, 100.0, 105.0, 110.0):
        for right in ("C", "P"):
            cid = f"{right}{int(strike)}"
            mid = float(
                price(
                    SPOTS[day], strike, (expiry - DAYS[day]).days / 365, 0.0, 0.0, VOL, right == "C"
                )
            )
            bid = 0.0 if cid in (zero_bid or set()) else max(mid - HALF, 0.0)
            rows.append({"instrument_id": f"OPT:{cid}", "underlying_id": A, "expiry": expiry,
                         "right": right, "strike": strike, "bid": bid,
                         "ask": mid + HALF})  # fmt: skip
    return pd.DataFrame(rows)


def chain(day: int, label: str | None = OK_LABEL, **kw: object) -> DayChain:
    return DayChain(
        DAYS[day], quotes(day, **kw) if label else None,  # type: ignore[arg-type]
        {A: SPOTS[day]} if label else {}, {A: label} if label else {}, None,
    )  # fmt: skip


def mid(day: int, cid: str, expiry: date = EXPIRY) -> float:
    return float(
        price(
            SPOTS[day],
            float(cid[1:]),
            (expiry - DAYS[day]).days / 365,
            0.0,
            0.0,
            VOL,
            cid[0] == "C",
        )
    )


def window(*legs: tuple[str, float, str, float], expiry: date = EXPIRY) -> Window:
    """A one-name window holding ``(right, qty, contract id, strike)`` legs."""
    cols = [
        LegColumn(right, qty, pd.Series([cid]), np.array([strike]), pd.Series([expiry]))
        for right, qty, cid, strike in legs
    ]
    return Window(pd.Series([A]), cols, np.array([True]), np.array([None], object),
                  np.array([None], object))  # fmt: skip


SPREAD = (("P", -1.0, "OPT:P100", 100.0), ("P", 1.0, "OPT:P95", 95.0))  # a put credit spread


def test_the_labels_are_the_chain_statuses_the_data_layer_uses() -> None:
    assert Labels() == Labels(OK_LABEL, STALE)  # this pure folder cannot import data: pinned here


def test_a_credit_spread_is_valued_mid_and_executable_at_entry_and_exit() -> None:
    w = window(*SPREAD)
    m = mark_window([chain(i) for i in range(3)], w)
    entry_mid = -mid(0, "P100") + mid(0, "P95")
    exit_mid = -mid(2, "P100") + mid(2, "P95")
    assert m.entry_mid[0] == pytest.approx(entry_mid) and m.exit_mid[0] == pytest.approx(exit_mid)
    # opening: the short leg sold at the bid, the long bought at the ask
    bid100 = max(mid(0, "P100") - HALF, 0.0)
    assert m.entry_exec[0] == pytest.approx(-bid100 + mid(0, "P95") + HALF)
    # closing: the short leg bought back at the ask, the long sold at the bid
    assert m.exit_exec[0] == pytest.approx(-(mid(2, "P100") + HALF) + (mid(2, "P95") - HALF))
    assert w.reason[0] is None and not m.at_expiry[0]


def test_a_leg_that_expires_on_the_exit_session_is_valued_at_intrinsic() -> None:
    expiry = DAYS[2]
    days = [
        DayChain(c.day, quotes(i, expiry), c.spots, c.labels, None)
        for i, c in enumerate(chain(i) for i in range(3))
    ]
    w = window(*SPREAD, expiry=expiry)
    m = mark_window(days, w)
    want = -max(100.0 - SPOTS[2], 0.0) + max(95.0 - SPOTS[2], 0.0)  # intrinsic, mid = executable
    assert m.exit_mid[0] == m.exit_exec[0] == pytest.approx(want) and m.at_expiry[0]


def test_the_hedge_delta_is_the_quantity_weighted_sum_of_the_models_own_deltas() -> None:
    m = mark_window([chain(i) for i in range(3)], window(*SPREAD))
    for k in (0, 1):
        t = (EXPIRY - DAYS[k]).days / 365
        short, long = (float(greeks(SPOTS[k], s, t, 0.0, 0.0, VOL, False).delta) for s in (100, 95))
        assert m.deltas[k][0] == pytest.approx(-short + long, abs=1e-6)


def test_a_zero_bid_at_the_exit_is_read_as_mid_ask_over_two_and_never_at_the_entry() -> None:
    days = [chain(0), chain(1), chain(2, zero_bid={"P95"})]
    w = window(*SPREAD)
    m = mark_window(days, w)
    ask95 = mid(2, "P95") + HALF
    assert m.exit_mid[0] == pytest.approx(-mid(2, "P100") + ask95 / 2)  # the exit fallback
    assert w.reason[0] is None
    entry = mark_window([chain(0, zero_bid={"P95"}), chain(1), chain(2)], window(*SPREAD))
    assert np.isnan(entry.entry_mid[0])  # the entry needs a real bid: no fallback


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"d2": chain(2, None)}, "NO_CHAIN:2026-10-07"),  # the name left the chain: a delisting
        ({"d2": chain(2, "STALE_DATA")}, "STALE_CHAIN:2026-10-07"),
    ],
)
def test_a_chain_that_left_or_went_stale_at_the_exit_is_unmeasured_never_filled(
    changes: dict[str, DayChain], reason: str
) -> None:
    days = [chain(0), chain(1), changes["d2"]]
    w = window(*SPREAD)
    mark_window(days, w)
    assert w.reason[0] == reason


def test_a_gap_between_entry_and_exit_costs_only_the_hedge() -> None:
    w = window(*SPREAD)
    m = mark_window([chain(0), chain(1, None), chain(2)], w)
    assert w.reason[0] is None and w.hedge[0] == "NO_CHAIN:2026-10-06"
    assert np.isfinite(m.exit_mid[0])
    quiet = window(*SPREAD)
    mark_window([chain(0), chain(1, zero_bid={"P100", "P95"}), chain(2)], quiet)
    assert quiet.reason[0] is None


def test_a_window_needs_option_legs_and_a_missing_entry_quote_is_a_reason() -> None:
    with pytest.raises(ValueError, match="at least one option leg"):
        Window(
            pd.Series([A]), [], np.array([True]), np.array([None], object), np.array([None], object)
        )
    bad = LegColumn("S", 1.0, pd.Series(["x"]), np.array([1.0]), pd.Series([EXPIRY]))
    with pytest.raises(ValueError, match="a call or a put"):
        Window(
            pd.Series([A]),
            [bad],
            np.array([True]),
            np.array([None], object),
            np.array([None], object),
        )
    w = window(*SPREAD)
    mark_window([chain(0, zero_bid={"P95"}), chain(1), chain(2)], w)
    assert w.reason[0] == "NO_ENTRY_QUOTE"
