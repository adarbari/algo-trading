"""A multi-stage position's cycle state (ADR 0088, X7, backend-concepts-2 §2.11, EF-G13): one
name's chain of stored option rows where the way a row ends decides the next phase, as the trades
of the ``slots`` book (``ladder.py``). The wheel (a cash-secured put, on assignment covered calls
until the shares are called away) is ``WHEEL``; a collar roll or a covered strangle is another
transition table over the same code.

Pure chaining over rows already read and valued (``time_series/cycle.py`` reads them); no pricing
and no lookahead. Placements are the sessions a phase can start (the session after an expiry);
each row's exit is the expiry it was held to, so the next placement is after it and one slot is
never in two phases.

- An assignment is learned after the close: the phase after an ``ASSIGNED`` row enters the next
  session (``later``), one after an expiry that was not assigned enters at the placement itself
  (the Cboe roll). So the shares of an assigned put are held overnight from the expiry's close to
  the call's entry, and a called-away call's put never enters before the shares are gone.
- ``Transitions`` maps ``(phase, assigned)`` to the next phase (``assigned``: the row's
  ``exit_kind`` was ``ASSIGNED``); the cycle starts, and restarts after a break, in ``start``.
- The cycle's capital is the opening phase's collateral, held across its phases: a phase's value
  is its net dollar P&L over that capital.
- Shares held across the gap between one row's last close and the next row's entry move: ``(entry
  spot - last spot) x shares`` is booked to the phase that holds them, so a wheel sums to premium
  - strike + the last share price, the put's intrinsic loss counted once (in the put row).
- A phase with no row, an UNMEASURED one, or a missing spot ends the cycle: the slot is cash, the
  reason is counted, a fresh cycle starts at the next placement (never a filled value, never a
  carried guess of the shares' fate)."""

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

PUT, CALL = "put", "call"
Transitions = Mapping[tuple[str, bool], str]  # (phase, row assigned) -> the next phase
WHEEL: Transitions = {(PUT, False): PUT, (PUT, True): CALL, (CALL, False): CALL, (CALL, True): PUT}
NO_ROW = "no_cycle_row"  # no stored row for the phase at its placement
GATE_UNKNOWN = "gate_unknown"  # the setup's gate could not be read at the entry's decision
NO_SPOT = "no_cycle_spot"  # shares are held over the gap and a spot at its ends is missing


@dataclass(frozen=True)
class CycleRow:
    """One stored, valued row of a phase: its ``entry`` and ``exit`` sessions, ``pnl`` the net
    dollars (option and share legs, costs in), ``stock`` the share leg's part of it, ``assigned``
    (``exit_kind`` ``ASSIGNED``), ``collateral`` (a put's: strike x contracts), ``entry_spot`` and
    ``last_spot`` (the underlying at entry and at the last close held, None when not stored) and
    ``shares`` held by a call row (a put row 0)."""

    entry: date
    exit: date
    pnl: float
    stock: float
    assigned: bool
    collateral: float
    entry_spot: float | None
    last_spot: float | None
    shares: float = 0.0


@dataclass(frozen=True)
class CycleTrade:
    """One phase of a cycle as a book trade: ``value`` its return on the cycle's capital, split
    into ``option`` and ``stock`` (``value`` is their sum)."""

    phase: str
    entry: date
    exit: date
    value: float
    option: float
    stock: float


def chain(
    rows: Mapping[str, Mapping[date, CycleRow | None]],
    placements: Sequence[date],
    later: Callable[[date], date],
    may_start: Callable[[date], bool | None],
    transitions: Transitions = WHEEL,
    start: str = PUT,
) -> tuple[tuple[CycleTrade, ...], Counter[str]]:
    """The cycle over ``placements`` (ascending) from ``rows`` by phase, each the row entered on a
    session (``None``: a stored but UNMEASURED row; a session absent: no row): ``(trades, lost)``,
    ``lost`` counting the phases dropped by reason. ``later``: the session after one;
    ``may_start``: whether a new cycle may open on a session (the setup's gate, None when it
    is unknown there; a cycle in progress is never cut by it)."""
    trades: list[CycleTrade] = []
    lost: Counter[str] = Counter()
    state, capital, last_spot = start, 0.0, None
    free, assigned = None, False  # the last exit, and whether it was an assignment
    for s in placements:
        entry = later(s) if assigned else s
        if free is not None and entry < free:
            continue
        if state == start:
            opens = may_start(entry)  # None: the gate is UNKNOWN there, a gap and not a decision
            if opens is None:
                lost[GATE_UNKNOWN] += 1
            if not opens:  # gated: the slot waits in cash
                assigned = False  # an earlier assignment is long known by the next placement
                continue
        row = rows.get(state, {}).get(entry)
        if row is None:
            lost[NO_ROW] += 1
            state, last_spot, free, assigned = start, None, None, False
            continue
        gap = 0.0
        if row.shares:  # shares carried over the gap from the last row's close
            if row.entry_spot is None or last_spot is None:
                lost[NO_SPOT] += 1
                state, last_spot, free, assigned = start, None, None, False
                continue
            gap = (row.entry_spot - last_spot) * row.shares
        if state == start:  # the opening phase of a cycle sets its capital
            capital = row.collateral
        if capital <= 0:
            lost[NO_ROW] += 1
            state, last_spot, free, assigned = start, None, None, False
            continue
        stock = (row.stock + gap) / capital
        total = (row.pnl + gap) / capital
        trades.append(CycleTrade(state, row.entry, row.exit, total, total - stock, stock))
        free, last_spot, assigned = row.exit, row.last_spot, row.assigned
        state = transitions[state, row.assigned]
    return tuple(trades), lost


def stock_share(trades: Sequence[CycleTrade]) -> dict[str, float | None]:
    """The wheel's return split: ``stock_return`` and ``option_return`` the summed returns on
    capital of the share and the option legs, ``stock_share`` the stock part of their sum (None
    when the total is not positive: a share of a loss or of nothing says nothing)."""
    stock = sum(t.stock for t in trades)
    option = sum(t.option for t in trades)
    total = stock + option
    return {
        "stock_return": stock,
        "option_return": option,
        "stock_share": stock / total if total > 0 else None,
    }
