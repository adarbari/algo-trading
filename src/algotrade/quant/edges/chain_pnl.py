"""The maths of a chain P&L (ADR 0053 amendment, EB H13): what an option structure held from one
session's close to a later one earned, from quoted prices, and its daily delta hedge. Pure numpy.

A position is a call weight and a put weight (a straddle is 1 and 1, a put 0 and 1), held long;
a short position is its negative and is applied by the harness. Quotes, never a model price:

- ``long_pnl``: per share, mid in and mid out, and executable (bought at the ask, sold at the bid;
  at expiry the intrinsic value is both);
- ``leg_delta``: our own Black-Scholes delta (r = q = 0, ``t`` in years of calendar days) at the
  vol the leg's mid implies (``implied_vol``); where no vol solves, the limit of a leg far out of
  or in the money (0, +-1), else NaN: the hedge is never taken from a delta we cannot compute;
- ``hedged_pnl``: the long position's mid P&L less the gain of a stock hedge rebalanced at each
  close, ``sum(delta_k * (S_{k+1} - S_k))`` over the sessions of the window (``delta_k`` the
  position's net delta at session ``k``'s close, the hedge held to the next close). No financing,
  no hedge cost, no vendor Greek.
"""

import numpy as np

from algotrade.quant.black_scholes import Array, ArrayLike, greeks
from algotrade.quant.implied_vol import IVStatus, implied_vol


def intrinsic(spot: ArrayLike, strike: ArrayLike, is_call: ArrayLike) -> Array:
    """An option's value at expiry: ``max(S - K, 0)`` for a call, ``max(K - S, 0)`` for a put."""
    s = np.asarray(spot, dtype=np.float64)
    k = np.asarray(strike, dtype=np.float64)
    return np.asarray(np.where(np.asarray(is_call, dtype=bool), s - k, k - s).clip(min=0.0))


def long_pnl(
    entry_mid: ArrayLike,
    entry_ask: ArrayLike,
    exit_mid: ArrayLike,
    exit_bid: ArrayLike,
    entry_spot: ArrayLike,
) -> tuple[Array, Array, Array]:
    """``(per_premium, exec_per_premium, per_underlying)`` of a long position: the mid P&L over
    the entry mid, the P&L bought at the ask and sold at the bid over the ask, and the mid P&L
    over the entry spot. NaN where an input is missing; a zero premium is NaN, never a zero."""
    em, ea, xm, xb, s0 = (
        np.asarray(a, dtype=np.float64)
        for a in (entry_mid, entry_ask, exit_mid, exit_bid, entry_spot)
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        mid = np.where(em > 0, (xm - em) / em, np.nan)
        executable = np.where(ea > 0, (xb - ea) / ea, np.nan)
        per_underlying = np.where(s0 > 0, (xm - em) / s0, np.nan)
    return mid, executable, per_underlying


def leg_delta(
    mid: ArrayLike, spot: ArrayLike, strike: ArrayLike, t_years: ArrayLike, is_call: ArrayLike
) -> Array:
    """Our own delta of each leg from its mid (r = q = 0). Where no vol solves, the limit of the
    delta when the price says the option is far from the money: 0 for a strictly out-of-the-money
    leg priced inside its no-arbitrage bound, +1 (call) or -1 (put) for an in-the-money leg priced
    at or below its intrinsic value. NaN otherwise (a missing mid, an ATM price with no vol, a
    price above its bound)."""
    m, s, k, t = (np.asarray(a, dtype=np.float64) for a in (mid, spot, strike, t_years))
    call = np.asarray(is_call, dtype=bool)
    solved = implied_vol(m, s, k, t, 0.0, 0.0, call)
    ok = solved.status == IVStatus.OK
    sigma = np.where(ok, solved.iv, 1.0)  # a placeholder where unsolved: masked below
    delta = greeks(s, k, t, 0.0, 0.0, sigma, call).delta
    with np.errstate(invalid="ignore"):
        otm = np.where(call, k > s, k < s)
        inside = (m >= 0) & (m <= np.where(call, s, k))
        itm_flat = ~otm & (np.abs(s - k) > 0) & (m <= intrinsic(s, k, call) * (1 + 1e-6) + 1e-9)
    limit = np.where(otm & inside, 0.0, np.where(itm_flat, np.where(call, 1.0, -1.0), np.nan))
    return np.asarray(np.where(ok, delta, limit), dtype=np.float64)


def hedged_pnl(entry_value: ArrayLike, exit_value: ArrayLike, spots: Array, deltas: Array) -> Array:
    """The long position's mid P&L less the hedge's gain, per row: ``spots`` is ``(n, k + 1)``
    (the underlying at each close from the entry to the exit), ``deltas`` ``(n, k)`` (the
    position's net delta at each close but the last). NaN where any spot or delta is."""
    gain = (np.asarray(deltas, dtype=np.float64) * np.diff(spots, axis=1)).sum(axis=1)
    return np.asarray(
        np.asarray(exit_value, dtype=np.float64) - np.asarray(entry_value, dtype=np.float64) - gain,
        dtype=np.float64,
    )
