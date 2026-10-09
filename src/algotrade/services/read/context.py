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
from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from functools import cached_property
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.data.reference import Snapshot, snapshot
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.services.features import catalogue
from algotrade.services.read.availability.cause import UnavailableKind, table_cause
from algotrade.services.read.session import Grain, NotFoundError, Session, grain_of, resolve_session
from algotrade.services.read.values import KIND_OF_CODE, Unknown, UnknownCode
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


STRING_CELL_BYTES = 60  # what a Python string in an object column costs, about

SLOT_BYTES = 8  # a pointer in a tuple, list or dict
MAX_CACHE_BYTES = 400 * 1024 * 1024  # the frames a cache holds, together (the hosted API's RSS)


def weigh(value: Any) -> int:
    """About how many bytes ``value`` holds: a DataFrame's buffers, a container's slots
    (``SLOT_BYTES`` each) and what they hold, a string's characters; any other object weighs
    nothing (the cache's count bound covers it). Cheap: no deep walk of a frame's strings, an
    object column's cells are priced at ``STRING_CELL_BYTES``. Records (a dict per row) are
    priced too: a page's value rows held as records weighed nothing before."""
    if isinstance(value, pd.DataFrame):
        # only a NumPy object column holds Python strings ``memory_usage`` cannot see; the
        # string dtype (pandas 3's default) and categoricals are counted from their buffers
        objects = sum(1 for t in value.dtypes if isinstance(t, np.dtype) and t.kind == "O")
        return int(value.memory_usage(index=True, deep=False).sum()) + (
            STRING_CELL_BYTES * len(value) * objects
        )
    if isinstance(value, str):
        return len(value)
    if isinstance(value, tuple | list):
        return SLOT_BYTES * len(value) + sum(weigh(v) for v in value)
    if isinstance(value, dict):
        return 2 * SLOT_BYTES * len(value) + sum(weigh(v) for v in value.values())
    return 0


class ResultCache:
    """A small LRU of computed results, bounded by entries and by the bytes of the frames it
    holds (``max_bytes``: one page can leave dozens of megabytes per screener behind, and a
    publish leaves the old entries until they age out). Callers key on
    ``StoreReader.visible_seq()`` (read before computing), so a publish makes every earlier
    entry unreachable (ADR 0022). One cache serves every caller of the API (ADR 0040): a
    result that depends on the request's user has ``ctx.user.user_id`` in its key, and one
    that depends on their catalogue (a user feature's formula) also ``catalogue_key(ctx)``, so
    an edited feature never hits a stale entry; stored rows of a named run (the run names its
    owner) and market data need not."""

    def __init__(self, size: int = 32, max_bytes: int = MAX_CACHE_BYTES) -> None:
        self._size = size
        self._max_bytes = max_bytes
        self._items: OrderedDict[Hashable, Any] = OrderedDict()
        self._weights: dict[Hashable, int] = {}
        self._held = 0
        self._lock = threading.Lock()
        self._flights: dict[Hashable, threading.Lock] = {}

    def get_or_compute(self, key: Hashable, compute: Callable[[], Any]) -> Any:
        """The entry under ``key``, computed once by ``compute()`` (never ``None``) when it is
        missing: concurrent callers missing the same key wait for the first one's result
        instead of each computing it (a hundred cold requests for the regime page's history
        would each read 14 000 partitions and hold their own frame). Another key never waits.
        A failed compute raises to its caller; a waiter then computes in turn."""
        found = self.get(key)
        if found is not None:
            return found
        with self._lock:
            flight = self._flights.setdefault(key, threading.Lock())
        try:
            with flight:
                found = self.get(key)
                if found is None:
                    found = compute()
                    self.put(key, found)
                return found
        finally:
            with self._lock:
                if self._flights.get(key) is flight:
                    del self._flights[key]

    def get(self, key: Hashable) -> Any | None:
        with self._lock:
            if key not in self._items:
                return None
            self._items.move_to_end(key)
            return self._items[key]

    def put(self, key: Hashable, value: Any) -> None:
        weight = weigh(value)
        with self._lock:
            self._held -= self._weights.pop(key, 0)
            self._items[key] = value
            self._items.move_to_end(key)
            self._weights[key] = weight
            self._held += weight
            # the newest entry stays even when it alone is over the byte bound
            while len(self._items) > 1 and (
                len(self._items) > self._size or self._held > self._max_bytes
            ):
                old, _ = self._items.popitem(last=False)
                self._held -= self._weights.pop(old, 0)


@dataclass(frozen=True)
class ReadContext:
    """One request's reads: market data (read-only), configs, whose they are, the session
    every value is for, the caller's catalogue (read once per request), the result cache
    (shared across requests; entries keyed on the published state) and ``loaders``: the
    GraphQL layer's per-request dataloaders (``algotrade_api.graphql.loaders``; None outside
    a GraphQL request, which loaders never need) and ``memo``, the request's own scratch for a
    result several loaders of it ask for (never shared across requests)."""

    reader: StoreReader
    configs: ConfigStore
    user: UserContext
    session: Session
    features: FeatureSet = field(repr=False)
    cache: ResultCache = field(compare=False, repr=False)
    loaders: Any = field(default=None, compare=False, repr=False)
    # What one request derived from the session's rows, by key (keys carry the session date:
    # ``at_session`` shares it): a loader asked for the same thing twice computes it once.
    memo: dict[Hashable, Any] = field(default_factory=dict, compare=False, repr=False)

    @cached_property
    def failed_tables(self) -> frozenset[str]:
        """The tables a failure stands behind for the session (a nightly step that did not
        SUCCEED, a table with no partition, and the groups that read one): ADR 0056."""
        # a function-level import: explain imports this module (a cycle at module level)
        from algotrade.services.read.availability.explain import failed_tables  # noqa: PLC0415

        return failed_tables(self.reader, self.session.date, self.session.missing, self.cache)

    def kind_of(self, code: UnknownCode, *tables: str) -> UnavailableKind:
        """The public kind of a gap of ``code`` in ``tables``: SYSTEM when a failure stands
        behind any of them, else the code's own kind (NO_ROW / NULL with none: NOT_STORED)."""
        if any(t in self.failed_tables for t in tables):
            return UnavailableKind.SYSTEM
        return KIND_OF_CODE[code]


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
    session: Session = cache.get_or_compute(key, lambda: resolve_session(reader, requested))
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
    absent = Unknown(
        UnknownCode.NO_PARTITION,
        table_cause(table, f"{table} has no partition for {day.isoformat()}", session=day),
    )
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
    """Every date ``table`` has a partition for, oldest first (an inventory, not a pick).
    Kept until the next publish, as the resolved session is: listing stats every partition
    directory of the table (the ingestion grid's 47 tables: 73 000 of them, 5.6 s). One cache
    entry holds every table's listing, so the grid does not evict the pages' entries."""
    if ctx.reader.own_run is not None:  # its pending writes add dates without a publish
        return tuple(ctx.reader.dates(table))
    key = ("stored-dates", ctx.reader.visible_seq())  # read before listing (ADR 0022)
    listed: dict[str, tuple[date, ...]] = ctx.cache.get_or_compute(key, dict)
    if table not in listed:
        listed[table] = tuple(ctx.reader.dates(table))
    return listed[table]


def partition_on(ctx: Stores, table: str, day: date) -> pd.DataFrame | None:
    """``table``'s partition for exactly ``day``, whatever its grain (``None``: none stored):
    an ops loader counting what is stored on each session of a window it names."""
    return ctx.reader.table(table, day)


def snapshot_on(ctx: Stores, table: str, day: date) -> Snapshot | None:
    """The snapshot of ``table`` a read for ``day`` sees (ADR 0007's one rule,
    ``data.reference.snapshot``); ``None``: the table has no partition at all."""
    return snapshot(ctx.reader, table, day)
