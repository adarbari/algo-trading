"""Which instruments a session's verification covers (deterministic, from stored data only).

1. ``core_symbols`` (``verification.toml``): always, in that order;
2. every instrument with a split, a dividend, a symbol change or a name / id change whose
   event date is the session (where a stored value is most likely to break);
3. ``rotating`` more, chosen from the instruments with a ``price_stats@v1`` row that session
   by a hash of (session, instrument id): the same session always picks the same names, and
   over many sessions every name gets its turn.

Only plain tickers (``AAPL``, ``BRK.B``) are sampled from the universe: preferreds, units and
warrants have no IB stock contract under our spelling.
"""

import hashlib
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from algotrade.data import StoreReader
from algotrade.data.events import read_events
from algotrade.data.resolver import SymbolResolver

EVENT_TABLES = ("events/split", "events/dividend", "events/reference_change")
SYMBOL_HISTORY = "instruments/symbol_history"
REFERENCE_CHANGES = ("renamed", "id_changed")  # a ticker change shows in symbol_history
PLAIN = re.compile(r"^[A-Z]{1,6}(\.[A-Z])?$")


@dataclass(frozen=True)
class Pick:
    symbol: str
    instrument_id: str
    why: str  # core | event | rotating | requested


def event_ids(reader: StoreReader, session: date) -> list[str]:
    """Instruments with a corporate action, symbol or reference change dated ``session``."""
    found: list[str] = []
    for table in (*EVENT_TABLES, SYMBOL_HISTORY):
        frame = read_events(reader, table, session, session).frame
        if table == "events/reference_change" and "change" in frame.columns:
            frame = frame[frame["change"].isin(REFERENCE_CHANGES)]
        found += [str(i) for i in frame["instrument_id"]]
    return sorted(set(found))


def rank(session: date, instrument_id: str) -> str:
    """A stable pseudo-random rank of an instrument for a session."""
    text = f"{session.isoformat()}:{instrument_id}".encode()
    return hashlib.blake2b(text, digest_size=8).hexdigest()


def choose(
    resolver: SymbolResolver,
    session: date,
    core: Sequence[str],
    rotating: int,
    events: Iterable[str],
    candidates: Iterable[str],
) -> list[Pick]:
    """Core symbols, then event instruments, then ``rotating`` hashed picks; no repeats."""
    picks: dict[str, Pick] = {}
    for symbol in core:
        iid = resolver.id_for(symbol)
        picks.setdefault(iid, Pick(symbol, iid, "core"))
    for iid in events:
        known = resolver.symbol_for(iid)
        if known and PLAIN.match(known):
            picks.setdefault(iid, Pick(known, iid, "event"))
    pool = [
        iid
        for iid in sorted(set(candidates) - set(picks))
        if (s := resolver.symbol_for(iid)) and PLAIN.match(s)
    ]
    for iid in sorted(pool, key=lambda i: rank(session, i))[:rotating]:
        picks[iid] = Pick(str(resolver.symbol_for(iid)), iid, "rotating")
    return list(picks.values())


def requested(resolver: SymbolResolver, symbols: Sequence[str]) -> list[Pick]:
    """``--symbols``: exactly those, in order."""
    return [Pick(s.upper(), resolver.id_for(s.upper()), "requested") for s in symbols]
