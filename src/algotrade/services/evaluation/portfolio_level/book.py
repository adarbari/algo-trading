"""One decision session's portfolio row from the setup's own trades (ADR 0088, G15).

A trade is open at D when ``entry_session <= D < exit_session``: a trade that exits at D's close is
already closed at D, and one entering after D is pending and never counts. Every open trade counts
equally (no size exists, ADR 0083). A field is ``None`` (UNKNOWN to a rule, never a pass) when it
needs a fact that is missing: an open trade's sector or collateral, or a trade whose exit is not
known although its planned exit has passed. If any open trade is priced from licensed history the
whole row is ``None`` (``personal_book``): the level is declared open, so the gate stays open-only
and a portfolio rule reads UNKNOWN on the history range, as the VIX-family values do."""

from collections import Counter
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from algotrade.config.edges.positions.fields import BOTH
from algotrade.config.strategy.portfolio_fields import PORTFOLIO_FIELDS
from algotrade.core.model.fields import portfolio_field
from algotrade.services.licences import OPEN

PERSONAL_BOOK = "personal_book"
EXIT_UNKNOWN = "exit_unknown"


@dataclass(frozen=True)
class OpenTrade:
    """One of the setup's trades: its name, entry and exit sessions (``exit_session`` None while
    not known, ``planned_exit`` the session it is due to close), collateral and the licence of the
    prices that value it."""

    instrument_id: str
    entry_session: date
    exit_session: date | None
    planned_exit: date | None
    capital: float | None
    licence: str


@dataclass(frozen=True)
class PortfolioRow:
    """The level's values at one session by ``portfolio.<name>``; ``reason`` says why every one is
    None (``personal_book`` / ``exit_unknown``), else None."""

    values: Mapping[str, int | float | None]
    reason: str | None = None


def open_at(trades: Sequence[OpenTrade], decision: date) -> tuple[list[OpenTrade], bool]:
    """The trades open at ``decision`` and whether one is unsettled (entered, exit not known and
    its planned exit not after ``decision``): then the book cannot be known."""
    held: list[OpenTrade] = []
    unsettled = False
    for t in trades:
        if t.entry_session > decision:
            continue
        if t.exit_session is not None:
            if t.exit_session > decision:
                held.append(t)
        elif t.planned_exit is not None and t.planned_exit > decision:
            held.append(t)
        else:
            unsettled = True
    return held, unsettled


def _share_of_most(counts: Collection[int], total: int) -> float:
    return max(counts) / total if counts else 0.0


def portfolio_row(
    trades: Sequence[OpenTrade],
    decision: date,
    sectors: Mapping[str, str | None],
    *,
    option: bool = False,
) -> PortfolioRow:
    """The portfolio fields at ``decision`` over ``trades`` (``sectors``: instrument id -> sector
    at ``decision``; ``option``: the book is an option setup's, which also has ``open_collateral``).
    An empty book is a known state (0 trades, no concentration)."""
    names = [f.name for f in PORTFOLIO_FIELDS if option or f.applies == BOTH]
    held, unsettled = open_at(trades, decision)
    reason = EXIT_UNKNOWN if unsettled else None
    if any(t.licence != OPEN for t in held):
        reason = PERSONAL_BOOK
    if reason is not None:
        return PortfolioRow({portfolio_field(n): None for n in names}, reason)
    total = len(held)
    by_name = Counter(t.instrument_id for t in held)
    known = {t.instrument_id: sectors.get(t.instrument_id) for t in held}
    by_sector = Counter(known[t.instrument_id] for t in held)
    capital = [t.capital for t in held]
    values: dict[str, int | float | None] = {
        "open_positions": total,
        "effective_bets": 1 / sum((c / total) ** 2 for c in by_name.values()) if total else 0.0,
        "max_sector_share": _share_of_most(by_sector.values(), total)
        if all(known.values())
        else None,
        "max_name_share": _share_of_most(by_name.values(), total),
        "open_collateral": (
            None if any(c is None for c in capital) else float(sum(c for c in capital if c))
        ),
    }
    return PortfolioRow({portfolio_field(n): values[n] for n in names})
