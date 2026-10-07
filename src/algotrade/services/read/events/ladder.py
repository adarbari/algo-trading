"""The expiry ladder (ADR 0050, plan 5.1 point 3): the listed expiries 7 to 90 calendar days
out in the session's stored chain (``OptionChain.expiries``, exactly the session: ADR 0036),
each with the events ahead it spans. Computed here so the browser derives nothing (ADR 0038).

The spanning rule: an expiry spans every event dated on or before it, so an earnings report
after the close on the expiry date is inside it (a short option held to that expiry carries
it through the report session's close: the conservative reading). An expiry is ``clear`` when
it spans no event but market-structure days (the expiries and quarter ends themselves, which
every rung past them would otherwise span). The ``marked`` rung is the last clear one: the
longest expiry that still spans no earnings or macro event (none when no rung is clear)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from algotrade.services.read.events.ahead import MARKET_STRUCTURE, AheadEvent
from algotrade.services.read.instruments.chains import OptionExpiry

LADDER_DAYS = (7, 90)  # the expiries listed: calendar days from the session, inclusive


@dataclass(frozen=True)
class LadderRung:
    """One listed expiry: ``days`` calendar days from the session, the events it spans (on or
    before it, oldest first) and whether it is ``clear`` (spans none but market-structure
    days) and whether it is the ``marked`` one (the last clear rung)."""

    expiry: date
    days: int
    spans: tuple[AheadEvent, ...]
    clear: bool
    marked: bool


def ladder(
    expiries: Sequence[OptionExpiry], events: Sequence[AheadEvent]
) -> tuple[LadderRung, ...]:
    """The rungs of ``expiries`` within ``LADDER_DAYS``, each spanning ``events`` (sorted)."""
    low, high = LADDER_DAYS
    rungs: list[tuple[OptionExpiry, tuple[AheadEvent, ...], bool]] = []
    for expiry in sorted(expiries, key=lambda e: e.date):
        if not low <= expiry.days <= high:
            continue
        spans = tuple(e for e in events if e.date <= expiry.date)
        clear = all(e.kind == MARKET_STRUCTURE for e in spans)
        rungs.append((expiry, spans, clear))
    last = max((i for i, (_, _, clear) in enumerate(rungs) if clear), default=None)
    return tuple(
        LadderRung(e.date, e.days, spans, clear, i == last)
        for i, (e, spans, clear) in enumerate(rungs)
    )
