"""Open the stores read-only, and what every explore query shares: the session a date
resolves to, pages of rows, JSON-safe records and the not-found error."""

import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd

from algotrade.config.user import UserContext
from algotrade.core.model.errors import AlgoTradeError
from algotrade.data import StoreReader
from algotrade.data.reference import snapshot
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.services.features import catalogue
from algotrade.services.views import to_value
from algotrade.storage.configs.store import ConfigStore
from algotrade.storage.factory import open_backend, open_config_store
from algotrade.storage.tables.interfaces import Backend
from algotrade.storage.tables.schemas import COMMON, SCHEMA_VERSION

BARS = "bars/1d"
MAX_PAGE_SIZE = 1000


class NotFoundError(AlgoTradeError):
    """The thing asked for (an instrument, a run, a config, a partition) does not exist."""


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
class ReadStore:
    """What explore queries read: market data (read-only), configs, and whose configs."""

    reader: StoreReader
    configs: ConfigStore
    user: UserContext
    kind: str = "memory"  # the storage URL scheme (file, memory)
    cache: ResultCache = field(default_factory=ResultCache, compare=False, repr=False)
    # The Builder preview's field frames (``explore.preview.frame``): large, few, kept apart
    # so page queries never evict the frame an edit re-evaluates.
    preview_cache: ResultCache = field(
        default_factory=lambda: ResultCache(4), compare=False, repr=False
    )


def features_key(store: ReadStore) -> str:
    """The user's catalogue as text: an edited feature file must not hit a stale entry."""
    features = store_features(store)
    return repr(sorted((n, repr(e.definition)) for n, e in features.expressions.items()))


def cached[T](store: ReadStore, query: tuple[Any, ...], compute: Callable[[], T]) -> T:
    """``compute()`` once per (query, user catalogue, published state): a page of a query
    already computed is sliced from it. The commit sequence is read before computing, so a
    publish landing meanwhile stores the result under the older key and is never served."""
    key = (*query, store.user.user_id, features_key(store), store.reader.visible_seq())
    hit = store.cache.get(key)
    if hit is not None:
        return hit  # type: ignore[no-any-return]
    done = compute()
    store.cache.put(key, done)
    return done


def open_store(data_url: str, config_dir: str | Path, user: UserContext) -> ReadStore:
    """The store at ``data_url`` and the configs under ``config_dir``, for ``user``."""
    return store_over(open_backend(data_url), open_config_store(config_dir), user, data_url)


def store_features(store: ReadStore) -> FeatureSet:
    """The features ``store.user`` sees: the site's plus their own (``config/users/<id>/
    features``; ADR 0023 step 4). Read on each call, so an edited user file shows up."""
    return catalogue(store.configs, store.user.user_id)


def store_over(
    backend: Backend, configs: ConfigStore, user: UserContext, data_url: str = "memory://"
) -> ReadStore:
    """A ``ReadStore`` over an open backend (tests and embedding)."""
    return ReadStore(StoreReader(backend), configs, user, urlparse(data_url).scheme)


def partition_for(reader: StoreReader, table: str, on: date | None) -> date:
    """The partition of ``table`` a read for ``on`` sees: the latest on or before ``on`` (the
    latest stored when ``on`` is None). ``NotFoundError`` when there is none."""
    snap = snapshot(reader, table, on)
    if snap is None or snap.pre_snapshot:
        detail = f" on or before {on}" if on else ""
        raise NotFoundError(f"{table}: nothing stored{detail}")
    return snap.snapshot_date


def latest_session(reader: StoreReader) -> date | None:
    """The latest session with daily bars (else the latest reference snapshot)."""
    for table in (BARS, "instruments/reference"):
        snap = snapshot(reader, table)
        if snap is not None:
            return snap.snapshot_date
    return None


@dataclass(frozen=True)
class StoreInfo:
    storage: str
    latest_session: date | None
    tables: list[str]
    versions: dict[str, str]


def _version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:  # pragma: no cover - always installed in the workspace
        return "unknown"


def store_info(store: ReadStore) -> StoreInfo:
    """The storage kind, the latest session, the stored tables and the library versions."""
    return StoreInfo(
        storage=store.kind,
        latest_session=latest_session(store.reader),
        tables=store.reader.table_names(),
        versions={"algotrade": _version("algotrade"), "schema": str(SCHEMA_VERSION)},
    )


@dataclass(frozen=True)
class Page[T]:
    items: list[T]
    total: int
    page: int
    size: int


def paginate[T](rows: Sequence[T], page: int, size: int) -> Page[T]:
    """Rows ``(page - 1) * size`` onwards (``page`` is 1-based, ``size`` at most 1000)."""
    page, size = max(page, 1), min(max(size, 1), MAX_PAGE_SIZE)
    start = (page - 1) * size
    return Page(list(rows[start : start + size]), len(rows), page, size)


def record(
    values: "Mapping[Any, Any] | pd.Series[Any]", drop: Iterable[str] = ()
) -> dict[str, Any]:
    """JSON-safe ``{column: value}`` without the point-in-time stamps and ``drop``."""
    skip = {*COMMON, *drop}
    return {str(k): to_value(v) for k, v in values.items() if str(k) not in skip}


def records(frame: pd.DataFrame, drop: Iterable[str] = ()) -> list[dict[str, Any]]:
    """``record`` for every row of ``frame``."""
    dropped = tuple(drop)
    return [record(r, dropped) for r in frame.to_dict("records")]
