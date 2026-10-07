"""The event-study scope as of a session, resolved once (ADR 0050 decision 2).

``scoped_instruments`` is the one place that turns "who is in scope" into instrument ids:

- ``tier``: the names whose ``option_liquidity@v1`` row on the newest stored session on or
  before the asked one has ``short_put_ok`` (put tier A or B: the short-put names);
- ``list``: the symbols of the site list ``config/site/events/scope.toml``;
- ``requested``: symbols the caller adds (the ``--symbols`` of a task), treated like the list;
- ``reference``: the stock a scoped leveraged or inverse fund tracks
  (``fund_reference@v1.reference_instrument_id`` of the newest stored session on or before the
  asked one), when stored.

A listed or requested symbol becomes an id only through ``SymbolResolver`` of the session's
reference snapshot (ADR 0018), never built as an ``EQ:`` string. A symbol the snapshot does not
know is returned in ``unresolved``, never dropped silently and never fetched under a made-up
id. A name found by several reasons appears once with all of them.
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date

from algotrade.config.site.events.scope import Documents, load_event_scope
from algotrade.core.model.fields import rollup_table
from algotrade.data import StoreReader
from algotrade.data.reference import resolver
from algotrade.data.resolver import SymbolResolver
from algotrade.data.rollups import rollup_as_of

TIER, LIST, REQUESTED, REFERENCE = "tier", "list", "requested", "reference"
REASONS = (TIER, LIST, REQUESTED, REFERENCE)
LIQUIDITY = rollup_table("instrument", "option_liquidity@v1")
FUND_REFERENCE = rollup_table("instrument", "fund_reference@v1")


@dataclass(frozen=True)
class ScopedName:
    """One name in scope: its id, its ticker in the reference snapshot and why it is in scope
    (a subset of ``REASONS``, in that order)."""

    instrument_id: str
    symbol: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ScopedInstruments:
    """The scope for ``session``: names in the order list, requested, tier (by symbol), then
    references; the reference snapshot and the stored sessions the tiers and the fund links
    were read from (``None``: not stored); the listed and requested symbols it does not know."""

    session: date
    reference_snapshot: date | None
    tier_session: date | None
    link_session: date | None
    names: tuple[ScopedName, ...]
    unresolved: tuple[str, ...]

    @property
    def instrument_ids(self) -> tuple[str, ...]:
        return tuple(n.instrument_id for n in self.names)

    def reasons(self, instrument_id: str) -> tuple[str, ...]:
        """Why the instrument is in scope (empty: it is not)."""
        return next((n.reasons for n in self.names if n.instrument_id == instrument_id), ())


def _tier_ids(reader: StoreReader, session: date) -> tuple[date | None, list[str]]:
    """The short-put names of the newest ``option_liquidity@v1`` on or before ``session``."""
    found = rollup_as_of(reader, LIQUIDITY, session)
    if found is None or "short_put_ok" not in found[1].columns:
        return (found[0] if found else None), []
    day, rows = found
    ok = rows["short_put_ok"].fillna(False).astype(bool)
    return day, sorted(rows.loc[ok, "instrument_id"].astype(str).unique())


def _fund_references(
    reader: StoreReader, session: date, funds: Sequence[str]
) -> tuple[date | None, dict[str, str]]:
    """The stock each of ``funds`` tracks (``fund_reference@v1``; funds without one omitted)."""
    if not funds:
        return None, {}
    found = rollup_as_of(reader, FUND_REFERENCE, session, funds)
    if found is None or "reference_instrument_id" not in found[1].columns:
        return (found[0] if found else None), {}
    day, rows = found
    linked = rows[rows["reference_instrument_id"].notna()]
    pairs = zip(linked["instrument_id"], linked["reference_instrument_id"], strict=True)
    return day, {str(fund): str(stock) for fund, stock in pairs}


def _symbols(
    listed: Sequence[str], requested: Sequence[str], wanted: Collection[str]
) -> dict[str, str]:
    """Upper-cased symbols in order, each with its reason (the list's wins a repeat), of the
    ``wanted`` reasons only."""
    out: dict[str, str] = {}
    for reason, symbols in ((LIST, listed), (REQUESTED, requested)):
        if reason not in wanted:
            continue
        for symbol in (s.strip().upper() for s in symbols):
            if symbol and symbol not in out:
                out[symbol] = reason
    return out


def scoped_instruments(
    reader: StoreReader,
    configs: Documents | None,
    session: date,
    requested: Sequence[str] = (),
    reasons: Collection[str] = REASONS,
) -> ScopedInstruments:
    """The names in scope for ``session`` (``configs``: the config store holding the site list;
    ``None``: no list), with each one's reasons and the symbols that did not resolve.
    ``reasons`` asks for a subset of ``REASONS`` (default all: the event study's scope): a task
    with a request budget leaves ``tier`` out. ``reference`` adds the stocks tracked by the
    funds among the names the other reasons found. Everything is read as of ``session``: the
    reference snapshot, the tiers and the fund links each from their newest partition on or
    before it, never a later one."""
    unknown = sorted(set(reasons) - set(REASONS))
    if unknown:
        raise ValueError(f"unknown scope reasons {unknown}: expected a subset of {list(REASONS)}")
    listed = load_event_scope(configs).symbols if configs is not None and LIST in reasons else ()
    found: dict[str, list[str]] = {}  # instrument id -> reasons, in order of first appearance

    def add(instrument_id: str, reason: str) -> None:
        reasons = found.setdefault(instrument_id, [])
        if reason not in reasons:
            reasons.append(reason)

    resolved: SymbolResolver = resolver(reader, session)
    unresolved = []
    for symbol, reason in _symbols(listed, requested, reasons).items():
        if resolved.knows(symbol):
            add(resolved.id_for(symbol), reason)
        else:
            unresolved.append(symbol)
    tier_session, tier_ids = _tier_ids(reader, session) if TIER in reasons else (None, [])
    for instrument_id in sorted(tier_ids, key=lambda i: (resolved.symbols.get(i, i), i)):
        add(instrument_id, TIER)
    link_session, links = (
        _fund_references(reader, session, list(found)) if REFERENCE in reasons else (None, {})
    )
    for stock in dict.fromkeys(links[f] for f in found if f in links):
        add(stock, REFERENCE)
    names = tuple(
        ScopedName(i, str(resolved.symbols.get(i, "")), tuple(sorted(r, key=REASONS.index)))
        for i, r in found.items()
    )
    return ScopedInstruments(
        session, resolved.snapshot, tier_session, link_session, names, tuple(unresolved)
    )
