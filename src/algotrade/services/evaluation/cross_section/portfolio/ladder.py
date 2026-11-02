"""A named option sleeve's book (ADR 0088, G16, E8b): the ladder of its trades on fixed collateral
slots, the ``slots`` weighting of the book code (``weights.py``).

The slots are fixed before the run from the schedule alone: one per named instrument times the
ladder's depth, the most entries of one instrument a hold can overlap (``ladder_depth``, from the
placed entry sessions and the hold, never from which trades happened to be measured), so capital
is never sized from hindsight and the book is never levered. Each trade holds one slot's share of
the collateral; a slot no trade fills is cash and earns nothing here (the bills are the
benchmark's, ``evidence/benchmarks.py``).

The book's P&L is realised at each trade's exit (the option grain stores the exit, not a daily
mark): the equity of fixed capital is one plus the summed realised returns, in exit order, so the
drawdown is over realised exits (it understates a drawdown inside an open trade) and the worst
month is the worst calendar month of exits. A cohort is the trades entered at one session; its
value is the slot-weighted sum of their returns on collateral."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np

from algotrade.analytics.metrics import max_drawdown
from algotrade.config.edges.portfolio import SLOTS
from algotrade.services.evaluation.cross_section.portfolio.weights import book_weights


@dataclass(frozen=True)
class Cohort:
    """The trades entered at one session: ``entry`` S, the last ``exit`` among them and the
    cohort's slot-weighted return on the book's collateral."""

    entry: date
    exit: date
    value: float


def ladder_depth(entries: Sequence[date], hold: int, sessions: Sequence[date]) -> int:
    """The most of ``entries`` (one instrument's placed entry sessions) any one hold of ``hold``
    sessions overlaps: an entry is open on its own session and the ``hold - 1`` after it, so
    entries spaced by the hold give 1. ``sessions``: the exchange sessions they are among."""
    at = {d: i for i, d in enumerate(sessions)}
    index = sorted(at[d] for d in set(entries) if d in at)
    deepest = 0
    for k, i in enumerate(index):
        deepest = max(deepest, sum(1 for j in index[: k + 1] if j > i - hold))
    return deepest


def cohorts(
    trades: Sequence[tuple[str, date, date, float]], names: int, depth: int
) -> tuple[Cohort, ...]:
    """The book's cohorts from ``trades`` (``(instrument, entry, exit, return on collateral)``
    of the measured trades) over ``names`` named instruments and a ladder ``depth``: each trade
    ``1 / (names x depth)`` of the collateral (``book_weights`` with ``SLOTS``), by entry."""
    by_entry: dict[date, list[tuple[str, date, float]]] = {}
    for name, entry, exit_, value in trades:
        by_entry.setdefault(entry, []).append((name, exit_, value))
    out = []
    for entry in sorted(by_entry):
        held = by_entry[entry]
        returns = {name: value for name, _, value in held}
        weights, _ = book_weights(sorted(returns), SLOTS, {}, {}, names)
        value = sum(w * returns[n] for n, w in weights if n in returns) / depth
        out.append(Cohort(entry, max(e for _, e, _ in held), value))
    return tuple(out)


def book_figures(book: Sequence[Cohort], slots: int) -> dict[str, float | int | str | None]:
    """The book's ``max_drawdown`` (a positive fraction of the fixed capital, over realised
    exits), ``worst_month`` (the lowest summed return of the cohorts exiting in one calendar
    month, ``worst_month_of`` its ``YYYY-MM``), the cohorts counted and the ``slots``; None
    figures without a cohort."""
    ordered = sorted(book, key=lambda c: (c.exit, c.entry))
    if not ordered:
        return {"slots": slots, "cohorts": 0, "max_drawdown": None, "worst_month": None,
                "worst_month_of": None}  # fmt: skip
    equity = 1.0 + np.cumsum([c.value for c in ordered])
    months: dict[str, float] = {}
    for c in ordered:
        key = f"{c.exit.year:04d}-{c.exit.month:02d}"
        months[key] = months.get(key, 0.0) + c.value
    worst = min(months, key=lambda k: (months[k], k))
    return {
        "slots": slots,
        "cohorts": len(ordered),
        "max_drawdown": max_drawdown(np.concatenate([[1.0], equity])),
        "worst_month": months[worst],
        "worst_month_of": worst,
    }
