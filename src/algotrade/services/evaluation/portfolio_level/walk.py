"""The in-order walk of a setup's decision sessions (ADR 0088, G15): a portfolio rule makes each
decision depend on the trades of earlier ones, so a setup that reads ``portfolio.*`` is evaluated
one session after another, never in parallel chunks. Deterministic: the same sessions and the same
``decide`` give the same rows, and a trade decided at D enters the book only for later sessions."""

from collections.abc import Callable, Collection, Mapping, Sequence
from datetime import date
from itertools import pairwise

from algotrade.services.evaluation.portfolio_level.book import (
    OpenTrade,
    PortfolioRow,
    open_at,
    portfolio_row,
)


def walk_in_order(
    decisions: Sequence[date],
    decide: Callable[[date, PortfolioRow], Sequence[OpenTrade]],
    sectors_at: Callable[[date, Collection[str]], Mapping[str, str | None]],
    *,
    option: bool = False,
) -> dict[date, PortfolioRow]:
    """The portfolio row at each of ``decisions`` (ascending, no repeats), each ``decide(D, row)``
    returning the trades decided at D (they count from their own entry session). ``sectors_at``
    reads the open trades' sectors at D."""
    if any(a >= b for a, b in pairwise(decisions)):
        raise ValueError("decision sessions must be strictly ascending")
    book: list[OpenTrade] = []
    rows: dict[date, PortfolioRow] = {}
    for day in decisions:
        held, _ = open_at(book, day)
        row = portfolio_row(
            book, day, sectors_at(day, {t.instrument_id for t in held}), option=option
        )
        rows[day] = row
        book = [t for t in book if t.exit_session is None or t.exit_session > day]
        book.extend(decide(day, row))
    return rows
