"""The in-order walk of a setup's decision sessions (ADR 0088, G15): a portfolio rule makes each
decision depend on the trades of earlier ones, so a setup that reads ``portfolio.*`` is evaluated
one session after another, never in parallel chunks. Deterministic: the same sessions and the same
``decide`` give the same rows, and a trade decided at D enters the book only for later sessions.
``Book`` is the stateful form (a caller that measures a leg between sessions); ``walk_in_order``
the loop over it."""

from collections.abc import Callable, Collection, Mapping, Sequence
from datetime import date
from itertools import pairwise

from algotrade.services.evaluation.portfolio_level.book import (
    LEG_LOST,
    OpenTrade,
    PortfolioRow,
    open_at,
    portfolio_row,
    unknown_row,
)

type SectorsAt = Callable[[date, Collection[str]], Mapping[str, str | None]]


class Book:
    """A setup's own trades across its ascending decision sessions: ``row_at`` the portfolio row
    at a session, ``add`` the trades decided there (they count from their own entry session),
    ``lost`` a session whose leg could not be read (the book is then not known up to a date)."""

    def __init__(self, *, option: bool = False) -> None:
        self._option = option
        self._trades: list[OpenTrade] = []
        self._lost_until: date | None = None

    def row_at(self, day: date, sectors_at: SectorsAt) -> PortfolioRow:
        """The row at ``day`` (``sectors_at`` reads the open trades' sectors at ``day``); every
        field UNKNOWN with reason ``leg_lost`` through the date given to ``lost``. Trades closed
        by ``day`` leave the book: ``day`` only ascends."""
        if self._lost_until is not None and day <= self._lost_until:
            return unknown_row(LEG_LOST, option=self._option)
        held, _ = open_at(self._trades, day)
        row = portfolio_row(
            self._trades,
            day,
            sectors_at(day, {t.instrument_id for t in held}),
            option=self._option,
        )
        self._trades = [t for t in self._trades if t.exit_session is None or t.exit_session > day]
        return row

    def add(self, trades: Sequence[OpenTrade]) -> None:
        """Put the trades decided at the session just read into the book."""
        self._trades.extend(trades)

    def lost(self, until: date) -> None:
        """The book is not known through ``until`` (a lost leg's trades): every row up to and
        including that date is UNKNOWN, reason ``leg_lost``."""
        self._lost_until = until


def walk_in_order(
    decisions: Sequence[date],
    decide: Callable[[date, PortfolioRow], Sequence[OpenTrade]],
    sectors_at: SectorsAt,
    *,
    option: bool = False,
) -> dict[date, PortfolioRow]:
    """The portfolio row at each of ``decisions`` (ascending, no repeats), each ``decide(D, row)``
    returning the trades decided at D (they count from their own entry session). ``sectors_at``
    reads the open trades' sectors at D."""
    if any(a >= b for a, b in pairwise(decisions)):
        raise ValueError("decision sessions must be strictly ascending")
    book = Book(option=option)
    rows: dict[date, PortfolioRow] = {}
    for day in decisions:
        rows[day] = book.row_at(day, sectors_at)
        book.add(decide(day, rows[day]))
    return rows
