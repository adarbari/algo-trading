"""The figures of an option position (one trade of a setup's template) from its legs, written
once (ownership ``option-position-figures``): what the option idea page shows beside the example
position (plan O4). Pure numerics over numpy arrays; one row per option leg, ``qty`` signed
(negative: sold), prices per share, ``MULTIPLIER`` shares to a contract:

- **Most you can lose** (``max_loss``): the worst P&L at expiry over every underlying price from
  0 up, on the credit collected, as a positive amount of dollars per position; None when the
  position can lose without limit (a naked call). The payoff is piecewise linear, so its minimum
  sits at 0 or at a strike.
- **Theta a day** (``position_theta``): the sum of each leg's quantity x the feed's theta x
  ``MULTIPLIER``, dollars a day; NaN when a leg has none, never a partial sum.
- **Chance in the money** (``p_itm``): the risk-neutral chance (r = q = 0, ADR 0053's
  convention, ``premium.p_below``) a leg finishes in the money: a put's chance below the strike,
  a call's chance above it.
- **Chance of assignment** (``assignment_chance``): the chance at least one sold leg finishes in
  the money, from ``p_itm``: below the highest sold put's strike or above the lowest sold call's,
  the two disjoint while the put's strike is under the call's (their sum), certain when they
  overlap (a straddle: one of them always finishes in the money); long legs are never assigned.
- **One-sigma-day loss** (``one_sigma_day_loss``): the loss, in dollars, if the underlying moves
  by one day's implied move (the nearest-to-the-money leg's IV / sqrt(252)) in the worse
  direction at once, every leg repriced by Black-Scholes at its own IV (r = q = 0) and the shares
  marked to the move; 0 when neither direction loses.

NaN propagates from a missing price or IV. No bid or ask enters: every figure is derived from
the mid and the feed's own greeks."""

import numpy as np

from algotrade.quant.black_scholes import Array, price
from algotrade.quant.options.premium import p_below
from algotrade.quant.rates import DAYS_PER_YEAR

MULTIPLIER = 100  # shares to one option contract
TRADING_DAYS = 252  # a day's implied move is IV / sqrt(TRADING_DAYS)


def _intrinsic(spot: float, strike: Array, is_call: Array) -> Array:
    return np.where(is_call, np.maximum(spot - strike, 0.0), np.maximum(strike - spot, 0.0))


def _pnl_at_expiry(
    spot: float, qty: Array, strike: Array, is_call: Array, credit: float, shares: float,
    share_entry: float,
) -> float:  # fmt: skip
    options = float(np.sum(qty * _intrinsic(spot, strike, is_call))) * MULTIPLIER
    return options + credit * MULTIPLIER + shares * (spot - share_entry)


def max_loss(
    qty: Array, strike: Array, is_call: Array, net_credit: float, shares: float = 0.0,
    share_entry: float = 0.0,
) -> float | None:  # fmt: skip
    """The most the position can lose at expiry, dollars per position (positive), on the
    ``net_credit`` per share it collected (negative: a debit) and ``shares`` held from
    ``share_entry``; None when unbounded. NaN when an input is NaN."""
    if not np.isfinite(net_credit) or not np.all(np.isfinite(strike)):
        return float("nan")
    slope = float(np.sum(qty * is_call)) * MULTIPLIER + shares
    if slope < 0:
        return None
    nodes = [0.0, *map(float, strike)]
    worst = min(
        _pnl_at_expiry(s, qty, strike, is_call, net_credit, shares, share_entry) for s in nodes
    )
    return max(0.0, -worst)


def position_theta(qty: Array, theta: Array) -> float:
    """The position's theta in dollars a day: sum of qty x theta x ``MULTIPLIER``; NaN when any
    leg's theta is missing."""
    if not np.all(np.isfinite(theta)):
        return float("nan")
    return float(np.sum(qty * theta)) * MULTIPLIER


def p_itm(spot: float, strike: Array, iv: Array, days: Array, is_call: Array) -> Array:
    """Each leg's risk-neutral chance of finishing in the money (r = q = 0); NaN where the IV
    or the days to expiry are not positive."""
    t_years = np.asarray(days, dtype=np.float64) / DAYS_PER_YEAR
    below_put = p_below(spot, strike, iv, t_years, "put")
    below_call = p_below(spot, strike, iv, t_years, "call")
    return np.asarray(np.where(is_call, 1.0 - below_call, below_put), dtype=np.float64)


def assignment_chance(
    spot: float, strike: Array, iv: Array, days: Array, is_call: Array, qty: Array
) -> float:
    """The chance at least one sold leg (``qty < 0``) finishes in the money; 0 with no sold leg,
    NaN where a sold leg's IV or days are not positive. In [0, 1]."""
    sold = np.asarray(qty) < 0
    calls, puts = sold & np.asarray(is_call, dtype=bool), sold & ~np.asarray(is_call, dtype=bool)
    k = np.asarray(strike, dtype=np.float64)
    chance = p_itm(spot, k, iv, days, is_call)
    if not np.all(np.isfinite(chance[sold])):
        return float("nan")
    if puts.any() and calls.any() and k[puts].max() >= k[calls].min():
        return 1.0
    below = float(chance[puts][np.argmax(k[puts])]) if puts.any() else 0.0
    above = float(chance[calls][np.argmin(k[calls])]) if calls.any() else 0.0
    return min(below + above, 1.0)


def one_sigma_day_loss(
    spot: float, qty: Array, strike: Array, is_call: Array, iv: Array, days: Array,
    shares: float = 0.0,
) -> float:  # fmt: skip
    """The loss in dollars of the worse one-sigma day (see the module doc); NaN when a leg's IV
    or days are missing."""
    t_years = np.asarray(days, dtype=np.float64) / DAYS_PER_YEAR
    if not (np.all(np.isfinite(iv)) and np.all(t_years > 0) and np.all(iv > 0)):
        return float("nan")
    lead = int(np.argmin(np.abs(strike - spot)))
    move = spot * float(iv[lead]) / float(np.sqrt(TRADING_DAYS))

    def value(at: float) -> float:
        legs = price(at, strike, t_years, 0.0, 0.0, iv, is_call)
        return float(np.sum(qty * legs)) * MULTIPLIER + shares * at

    now = value(spot)
    worst = min(value(max(spot + move, 0.0)) - now, value(max(spot - move, 0.0)) - now)
    return max(0.0, -worst)
