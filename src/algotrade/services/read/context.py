"""What every loader reads through: the ``ReadContext`` of one request (the stores, whose
catalogue, the one resolved ``Session``, the result cache), opened by ``open_context``, and
``partition``, the only way a loader reads a session-grain table for the request's session
(ADR 0036 decision 6), and ``run_partition``, a run record's own results (the run names its
session: an explicit argument, never "latest"), and ``previous_session`` / ``at_session``: the
stored session of a table before the request's and a context for it (a loader comparing with
the previous run names that date explicitly, ADR 0036). The inventory reads (``stored_dates``,
``partition_on``, ``snapshot_on``) report what is stored on dates the caller names: only the ops
loader that describes storage itself calls them (the Admin completeness grid; READ 2's
``test_inventory_reads_only_in_the_completeness_loader``), never a loader of a fact.

``open_context`` resolves the session once per request (and reuses it while nothing is
published: keyed on ``StoreReader.visible_seq``); nothing else in ``services/read`` calls
``resolve_session`` (ownership ``session-resolution``). A loader reads ``ctx.session.date``
only: another date is a named argument of the loader, never derived."""

import threading
from collections import OrderedDict
from collections.abc import Hashable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.data.reference import Snapshot, snapshot
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.services.features import catalogue
from algotrade.services.read.session import Grain, NotFoundError, Session, grain_of, resolve_session
from algotrade.services.read.values import Unknown, UnknownCode
from algotrade.storage.configs.store import ConfigStore
from algotrade.storage.factory import open_backend, open_config_store
from algotrade.storage.runs import RunRecord

__all__ = [
    "ConfigStore",
    "NotFoundError",
    "ReadContext",
    "ResultCache",
    "StoreContext",
    "StoreReader",
    "Stores",
    "at_session",
    "open_context",
    "open_read_stores",
    "open_stores",
    "partition",
    "partition_on",
    "previous_session",
    "run_partition",
    "snapshot_on",
    "stored_dates",
]


class ResultCache:
    """A small LRU of computed results. Callers key on ``StoreReader.visible_seq()`` (read
    before computing), so a publish makes every earlier entry unreachable (ADR 0022). One
    cache serves every caller of the API (ADR 0040): a result that depends on the request's
    user has ``ctx.user.user_id`` in its key, and one that depends on their catalogue (a user
    feature's formula) also ``catalogue_key(ctx)``, so an edited feature never hits a stale
    entry; stored rows of a named run (the run names its owner) and market data need not."""

    def __init__(self, size: int = 8) -> None:
        self._size = size
        self._items: OrderedDict[Hashable, Any] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: Hashable) -> Any | None:
        with self._lock:
            if key not in self._items:
                return None
            self._items.move_to_end(key)
            return self._items[key]

    def put(self, key: Hashable, value: Any) -> None:
        with self._lock:
            self._items[key] = value
            self._items.move_to_end(key)
            while len(self._items) > self._size:
                self._items.popitem(last=False)


@dataclass(frozen=True)
class ReadContext:
    """One request's reads: market data (read-only), configs, whose they are, the session
    every value is for, the caller's catalogue (read once per request), the result cache
    (shared across requests; entries keyed on the published state) and ``loaders``: the
    GraphQL layer's per-request dataloaders (``algotrade_api.graphql.loaders``; None outside
    a GraphQL request, which loaders never need)."""

    reader: StoreReader
    configs: ConfigStore
    user: UserContext
    session: Session
    features: FeatureSet = field(repr=False)
    cache: ResultCache = field(compare=False, repr=False)
    loaders: Any = field(default=None, compare=False, repr=False)


@dataclass(frozen=True)
class StoreContext:
    """One request's stores without a session: what a loader of configs and run records reads
    (they are not session data, so they need no stored market data to resolve a session from:
    a fresh store still lists its configs and the user's drafts). The same fields as
    ``ReadContext`` minus ``session`` and ``loaders``."""

    reader: StoreReader
    configs: ConfigStore
    user: UserContext
    features: FeatureSet = field(repr=False)
    cache: ResultCache = field(compare=False, repr=False)


# What a session-free loader takes: a ``StoreContext``, or a ``ReadContext`` (a superset).
Stores = StoreContext | ReadContext


def catalogue_key(ctx: Stores) -> str:
    """The caller's expression features as text, for a cache key over their catalogue."""
    return repr(sorted((n, repr(e.definition)) for n, e in ctx.features.expressions.items()))


def open_read_stores(data_url: str, config_dir: str | Path) -> tuple[StoreReader, ConfigStore]:
    """The store at ``data_url`` (read-only) and the configs under ``config_dir``: what an app
    opens once and opens every request's context over (the API's ``deps.open_store``)."""
    return StoreReader(open_backend(data_url)), open_config_store(config_dir)


def open_stores(
    reader: StoreReader,
    configs: ConfigStore,
    user: UserContext,
    cache: ResultCache | None = None,
) -> StoreContext:
    """The session-free context of one request: ``user``'s catalogue read once."""
    return StoreContext(
        reader=reader,
        configs=configs,
        user=user,
        features=catalogue(configs, user.user_id),
        cache=cache if cache is not None else ResultCache(),
    )


def open_context(
    reader: StoreReader,
    configs: ConfigStore,
    user: UserContext,
    requested: date | None = None,
    cache: ResultCache | None = None,
) -> ReadContext:
    """The context of one request for ``requested`` (None: the latest session): resolves the
    session once and reads ``user``'s catalogue once. ``NotFoundError`` on an empty store when
    no date is asked for. ``cache``: the long-lived cache to share (default: a fresh one); the
    resolved session is kept in it until the next publish (resolving lists every expected
    table's partitions: ~26 ``dates()`` calls)."""
    cache = cache if cache is not None else ResultCache()
    return ReadContext(
        reader=reader,
        configs=configs,
        user=user,
        session=_session(reader, requested, cache),
        features=catalogue(configs, user.user_id),
        cache=cache,
    )


def _session(reader: StoreReader, requested: date | None, cache: ResultCache) -> Session:
    """The session ``requested`` resolves to, kept in ``cache`` until the next publish."""
    # Read before resolving (ADR 0022); a run's own pending writes do not move visible_seq.
    key = ("session", requested, reader.own_run, reader.visible_seq())
    session: Session | None = cache.get(key)
    if session is None:
        session = resolve_session(reader, requested)
        cache.put(key, session)
    return session


def previous_session(ctx: ReadContext, table: str) -> date | None:
    """The latest session before ``ctx.session.date`` with a stored partition of the
    session-grain ``table`` (None: none). The date a loader comparing with an earlier run
    names explicitly; never a fallback for a missing partition (ADR 0036)."""
    grain = grain_of(table)
    if grain is not Grain.SESSION:
        raise ValueError(f"{table} is {grain} grain: only session-grain tables have sessions")
    earlier = [d for d in ctx.reader.dates(table) if d < ctx.session.date]
    return max(earlier) if earlier else None


def at_session(ctx: ReadContext, day: date) -> ReadContext:
    """``ctx`` for the session ``day`` (an explicit date, e.g. ``previous_session``'s): the
    same stores, user, catalogue and cache; every read through it is for exactly ``day``."""
    return replace(ctx, session=_session(ctx.reader, day, ctx.cache), loaders=None)


def partition(
    ctx: ReadContext,
    table: str,
    columns: Sequence[str] | None = None,
    instruments: Sequence[str] | None = None,
) -> pd.DataFrame | Unknown:
    """``table``'s partition for exactly ``ctx.session.date``, else ``Unknown(NO_PARTITION)``;
    never an older partition. ``columns``: only these (plus the row key and the point-in-time
    columns); ``instruments``: only their rows (a stored partition with none of them is an
    empty frame, not UNKNOWN). ``ValueError`` for a table that is not session grain (snapshot,
    event, issuer-dated and incremental tables have their own rule: ``session.grain_of``)."""
    grain = grain_of(table)
    if grain is not Grain.SESSION:
        raise ValueError(f"{table} is {grain} grain: read it by its own rule, not partition()")
    day = ctx.session.date
    absent = Unknown(UnknownCode.NO_PARTITION, f"{table} has no partition for {day.isoformat()}")
    if columns is None and instruments is None:
        whole = ctx.reader.table(table, day)
        return absent if whole is None else whole
    if day not in ctx.reader.dates(table):
        return absent
    found = ctx.reader.table_range(table, day, day, None, instruments, columns)
    if found is None:  # the partition is stored; none of its rows is asked for
        return pd.DataFrame(columns=["instrument_id", *(columns or ())])
    if instruments is not None:  # the read prunes row groups only
        found = found[found["instrument_id"].isin(set(instruments))].reset_index(drop=True)
    return found


def run_partition(ctx: Stores, table: str, run: RunRecord) -> pd.DataFrame | None:
    """The rows ``run`` wrote to the session-grain ``table`` (a ``results/*`` table it
    publishes to its own end session), read as of the run: a later run with the same end
    session replaces the partition, so it is read as the run left it. ``None``: nothing
    stored for it. ``ValueError`` for a table that is not session grain."""
    grain = grain_of(table)
    if grain is not Grain.SESSION:
        raise ValueError(f"{table} is {grain} grain: a run's results are session grain")
    frame = ctx.reader.table(table, run.session_date, as_of=run.started_at)
    if frame is None:
        return None
    return frame[frame["run_id"] == run.run_id].reset_index(drop=True)


# ---------------------------------------------------------------------------- inventory
# What is stored, for the ops loaders that report on storage (services/read/ops): which dates a
# table has, one partition on a date the caller names, the snapshot a date sees. Never the
# partition a displayed fact is read from: that is ``partition`` (exactly the session).


def stored_dates(ctx: Stores, table: str) -> tuple[date, ...]:
    """Every date ``table`` has a partition for, oldest first (an inventory, not a pick)."""
    return tuple(ctx.reader.dates(table))


def partition_on(ctx: Stores, table: str, day: date) -> pd.DataFrame | None:
    """``table``'s partition for exactly ``day``, whatever its grain (``None``: none stored):
    an ops loader counting what is stored on each session of a window it names."""
    return ctx.reader.table(table, day)


def snapshot_on(ctx: Stores, table: str, day: date) -> Snapshot | None:
    """The snapshot of ``table`` a read for ``day`` sees (ADR 0007's one rule,
    ``data.reference.snapshot``); ``None``: the table has no partition at all."""
    return snapshot(ctx.reader, table, day)
