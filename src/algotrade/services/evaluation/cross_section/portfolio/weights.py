"""The weights of a portfolio_return book at one decision session (ADR 0074): from the picks, the
edge's weighting and what was read at D (the screen's scores, a declared volatility feature).

Fail closed: a book whose weights cannot be formed from what was known at D is *no book* (a
reason, the session is left out), never a silent re-weighting over the names that happen to have
an input (a missing volatility given zero weight would be a bet nobody declared).

- ``equal``: ``1 / n`` each.
- ``inverse_vol``: proportional to ``1 / vol``; every pick needs a finite positive volatility.
- ``score``: proportional to the screen's score; every pick needs a finite positive score (a
  score is a rank key, not a size: a non-positive one has no size to give).
- ``CASH`` among the picks is a position like any other with an equal share ``1 / n``; the
  names beside it share the rest by the weighting (cash has no score or volatility).
- No picks: all cash, a cash session (not an excluded one)."""

import math
from collections.abc import Mapping, Sequence

from algotrade.config.edges.portfolio import CASH, EQUAL, INVERSE_VOL, SCORE

NO_VOL = "no_vol"  # a pick has no finite positive volatility at D
NO_SCORE = "no_score"  # a pick has no finite positive score at D
Weights = tuple[tuple[str, float], ...]  # (instrument id or CASH, weight), summing to one


def _usable(value: float | None) -> bool:
    return value is not None and math.isfinite(value) and value > 0


def book_weights(
    picks: Sequence[str],
    weighting: str,
    scores: Mapping[str, float],
    vols: Mapping[str, float | None],
) -> tuple[Weights, str]:
    """``(weights, reason)``: the book of ``picks`` (in rank order) and ``""``, or ``()`` and why
    it cannot be formed. Weights add to one; the picks are distinct (a repeated one counts once)."""
    ids = list(dict.fromkeys(picks))
    if not ids:
        return ((CASH, 1.0),), ""
    names = [i for i in ids if i != CASH]
    cash = (1.0 / len(ids)) if CASH in ids else 0.0
    if weighting == EQUAL:
        raw = dict.fromkeys(names, 1.0)
    elif weighting == INVERSE_VOL:
        if not all(_usable(vols.get(i)) for i in names):
            return (), NO_VOL
        raw = {i: 1.0 / float(vols[i]) for i in names}  # type: ignore[arg-type]
    elif weighting == SCORE:
        if not all(_usable(scores.get(i)) for i in names):
            return (), NO_SCORE
        raw = {i: float(scores[i]) for i in names}
    else:
        raise ValueError(f"no weighting {weighting!r}")
    total = sum(raw.values())
    book = [(i, (1.0 - cash) * raw[i] / total) for i in names] if names else []
    if cash:
        book.append((CASH, cash))
    return tuple(book), ""
