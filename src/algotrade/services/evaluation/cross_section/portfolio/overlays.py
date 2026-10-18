"""The overlays of a portfolio_return book (ADR 0074 amendment): what is done to the weights of a
book once the weighting (and the ensemble average) has formed them.

``canary`` (ADR 0074 amendment item 17): a gate on the book. The canaries' ``field`` (a numeric
feature, for example a momentum score) is read at D, never at S; the share of them that is
negative, in units of ``breadth``, is the risk-off share ``f = min(1, bad / breadth)`` and the book
becomes ``(1 - f) * book + f * defensive``, the defensive asset being ``CASH`` or the defensive
ticker with the highest ``field`` at D (ties by ticker). A canary or, when ``f > 0``, a defensive
candidate the snapshot at D does not know or has no value for leaves the session out
(``no_canary:<T>``, ``no_defensive:<T>``): never read as positive, never skipped.

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
from collections.abc import Mapping, Sequence
from datetime import date
from typing import TYPE_CHECKING

import numpy as np

from algotrade.config.edges.document import Outcome
from algotrade.config.edges.portfolio import CASH, Canary
from algotrade.core.time.calendar import sessions_ending
from algotrade.services.evaluation.cross_section.portfolio.session import TRADING_DAYS
from algotrade.services.evaluation.cross_section.portfolio.weights import Weights

if TYPE_CHECKING:
    from algotrade.services.evaluation.cross_section.reads.session import SessionReads

NO_BOOK_VOL = "no_book_vol"  # a held name has no daily return on a session of the window
NO_CANARY = "no_canary"  # a canary is not a known instrument at D or has no value ("...:<ticker>")
NO_DEFENSIVE = "no_defensive"  # a defensive candidate has none ("...:<ticker>")


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


def risk_off_share(
    values: Mapping[str, float | None], tickers: Sequence[str], breadth: int
) -> float:
    """``min(1, bad / breadth)`` over the canaries: ``bad`` counts the strictly negative values
    (``values`` by ticker, every canary present and finite: checked by the caller)."""
    bad = sum(1 for t in tickers if (values[t] or 0.0) < 0)
    return min(1.0, bad / breadth)


def canary_blend(weights: Weights, share: float, defensive: str) -> Weights:
    """``(1 - share) * weights + share * defensive`` (``defensive``: an id or ``CASH``): adds to
    one, long only; a name held by both adds its shares; zero weights are dropped."""
    mixed: dict[str, float] = {}
    for name, weight in weights:
        mixed[name] = mixed.get(name, 0.0) + (1.0 - share) * weight
    if share > 0:
        mixed[defensive] = mixed.get(defensive, 0.0) + share
    return tuple((n, w) for n, w in mixed.items() if w > 0)


def _read(
    session: "SessionReads", tickers: Sequence[str], field_name: str, day: date, reason: str
) -> tuple[dict[str, float], str]:
    """The canary field of ``tickers`` at D by ticker, or ``{}`` and ``reason:<ticker>`` for the
    first one (in the order written) that is not a known instrument at D or has no finite value."""
    ids = session.instruments(tuple(tickers), day)
    found = session.numbers(field_name, frozenset(i for i in ids.values() if i), day)
    out: dict[str, float] = {}
    for ticker in tickers:
        value = found.get(ids.get(ticker) or "")
        if value is None or not math.isfinite(value):
            return {}, f"{reason}:{ticker}"
        out[ticker] = value
    return out, ""


def canary_gate(
    c: Canary, session: "SessionReads", day: date, weights: Weights
) -> tuple[Weights, float | None, str]:
    """``(weights, risk_off, reason)``: the book after the canary gate read at D."""
    values, why = _read(session, c.tickers, c.field, day, NO_CANARY)
    if why:
        return (), None, why
    share = risk_off_share(values, c.tickers, c.breadth)
    if share == 0:
        return weights, 0.0, ""
    if c.defensive == (CASH,):
        return canary_blend(weights, share, CASH), share, ""
    options, why = _read(session, c.defensive, c.field, day, NO_DEFENSIVE)
    if why:
        return (), None, why
    best = min(options, key=lambda t: (-options[t], t))  # the highest, ties by ticker
    held = session.instruments((best,), day)[best]
    return canary_blend(weights, share, str(held)), share, ""


def apply_overlays(
    o: Outcome, session: "SessionReads", day: date, weights: Weights
) -> tuple[Weights, float | None, float | None, str]:
    """``(weights, book_vol, risk_off, reason)``: the book after the outcome's overlays in their
    order (canary, then vol_target), the volatility it was scaled from (None: no vol_target, or an
    all-cash book), the canary's risk-off share (None: no canary), or ``()`` and why it cannot be
    formed. Without an overlay the book is returned as it is."""
    risk_off = None
    if o.canary is not None:
        weights, risk_off, why = canary_gate(o.canary, session, day, weights)
        if why:
            return (), None, None, why
    if o.vol_target is None:
        return weights, None, risk_off, ""
    ids = frozenset(i for i, _ in weights if i != CASH)
    if not ids:
        return weights, None, risk_off, ""
    days = sessions_ending(day, o.vol_window)
    sigma = book_volatility(weights, session.history(o.vol_return_field, ids, days), days)
    if sigma is None:
        return (), None, None, NO_BOOK_VOL
    return vol_scaled(weights, sigma, o.vol_target), sigma, risk_off, ""
