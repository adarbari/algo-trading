"""The overlays of a portfolio_return book (ADR 0074 amendment): what is done to the weights of a
book once the weighting (and the ensemble average) has formed them.

``vol_target``: the book is scaled down, never up, so that its annualised volatility, measured
from the daily returns of *today's* weights over the last ``vol_window`` sessions ending at D,
is at most the target: ``k = min(1, target / sigma)``, the names are multiplied by ``k`` and the
rest is cash (the T-bill yield), so no leverage and never a weight below zero.

Every daily return is the one a session ``t <= D`` read at ``t`` (``SessionReads.history``, through
the recording reader: a restated partition invalidates the legs), never a value stored later:
nothing after D enters. A name with no return on some session of the window leaves the session out
(``no_book_vol``): the book's volatility is never measured over the names that happen to have one.
A book that is all cash has no volatility and is left as it is."""

import math
from collections.abc import Sequence
from datetime import date
from typing import TYPE_CHECKING

import numpy as np

from algotrade.config.edges.document import Outcome
from algotrade.config.edges.portfolio import CASH
from algotrade.core.time.calendar import sessions_ending
from algotrade.services.evaluation.cross_section.portfolio.session import TRADING_DAYS
from algotrade.services.evaluation.cross_section.portfolio.weights import Weights

if TYPE_CHECKING:
    from algotrade.services.evaluation.cross_section.reads.session import SessionReads

NO_BOOK_VOL = "no_book_vol"  # a held name has no daily return on a session of the window


def book_volatility(
    weights: Weights, history: dict[date, dict[str, float | None]], days: Sequence[date]
) -> float | None:
    """The annualised volatility of the book's daily returns over ``days``: ``sqrt(252)`` times
    the sample standard deviation of ``sum(w_i * r_i,t)`` over the names (cash earns no
    variance). None when a name has no finite return on a session of ``days``, or there are fewer
    than two sessions; 0.0 for a book of no names."""
    names = [(i, w) for i, w in weights if i != CASH]
    if not names:
        return 0.0
    if len(days) < 2:
        return None
    daily = []
    for day in days:
        read = history.get(day, {})
        total = 0.0
        for name, weight in names:
            value = read.get(name)
            if value is None or not math.isfinite(value):
                return None
            total += weight * value
        daily.append(total)
    return float(np.std(daily, ddof=1) * math.sqrt(TRADING_DAYS))


def vol_scaled(weights: Weights, sigma: float, target: float) -> Weights:
    """``weights`` scaled by ``k = min(1, target / sigma)`` over the names, the rest cash (an
    existing cash share stays; the freed share joins it). Unchanged when the book is already at or
    under the target, or has no volatility; names keep their order."""
    if not sigma > target:
        return weights
    k = target / sigma
    names = [(i, w * k) for i, w in weights if i != CASH]
    cash = 1.0 - sum(w for _, w in names)
    return (*names, (CASH, cash))


def apply_overlays(
    o: Outcome, session: "SessionReads", day: date, weights: Weights
) -> tuple[Weights, float | None, str]:
    """``(weights, book_vol, reason)``: the book after the outcome's overlays, the volatility it
    was scaled from (None: no vol_target, or an all-cash book), or ``()`` and why it cannot be
    formed. Without an overlay the book is returned as it is."""
    if o.vol_target is None:
        return weights, None, ""
    ids = frozenset(i for i, _ in weights if i != CASH)
    if not ids:
        return weights, None, ""
    days = sessions_ending(day, o.vol_window)
    sigma = book_volatility(weights, session.history(o.vol_return_field, ids, days), days)
    if sigma is None:
        return (), None, NO_BOOK_VOL
    return vol_scaled(weights, sigma, o.vol_target), sigma, ""
