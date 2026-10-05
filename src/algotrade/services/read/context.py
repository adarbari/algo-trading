"""What every loader reads through: the ``ReadContext`` of one request (the stores, whose
catalogue, the one resolved ``Session``, the result cache), opened by ``open_context``, and
``partition``, the only way a loader reads a session-grain table (ADR 0036 decision 6).

``open_context`` resolves the session once per request (and reuses it while nothing is
published: keyed on ``StoreReader.visible_seq``); nothing else in ``services/read`` calls
``resolve_session`` (ownership ``session-resolution``). A loader reads ``ctx.session.date``
only: another date is a named argument of the loader, never derived."""

import threading
from collections import OrderedDict
from collections.abc import Hashable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.services.features import catalogue
from algotrade.services.read.session import Grain, NotFoundError, Session, grain_of, resolve_session
from algotrade.services.read.values import Unknown, UnknownCode
from algotrade.storage.configs.store import ConfigStore

__all__ = ["NotFoundError", "ReadContext", "ResultCache", "open_context", "partition"]


class ResultCache:
    """A small LRU of computed results. Callers key on ``StoreReader.visible_seq()`` (read
    before computing), so a publish makes every earlier entry unreachable (ADR 0022)."""

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
    # Read before resolving (ADR 0022); a run's own pending writes do not move visible_seq.
    key = ("session", requested, reader.own_run, reader.visible_seq())
    session = cache.get(key)
    if session is None:
        session = resolve_session(reader, requested)
        cache.put(key, session)
    return ReadContext(
        reader=reader,
        configs=configs,
        user=user,
        session=session,
        features=catalogue(configs, user.user_id),
        cache=cache,
    )


def partition(ctx: ReadContext, table: str) -> pd.DataFrame | Unknown:
    """``table``'s partition for exactly ``ctx.session.date``, else ``Unknown(NO_PARTITION)``;
    never an older partition. ``ValueError`` for a table that is not session grain (snapshot,
    event, issuer-dated and incremental tables have their own rule: ``session.grain_of``)."""
    grain = grain_of(table)
    if grain is not Grain.SESSION:
        raise ValueError(f"{table} is {grain} grain: read it by its own rule, not partition()")
    frame = ctx.reader.table(table, ctx.session.date)
    if frame is None:
        detail = f"{table} has no partition for {ctx.session.date.isoformat()}"
        return Unknown(UnknownCode.NO_PARTITION, detail)
    return frame
