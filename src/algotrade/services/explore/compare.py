"""Several instruments side by side (Explore compare, ``/explore/compare*``): their catalogue
features for one session, and their rebased daily closes on one date axis. A key is an
``instrument_id`` or a ticker (resolved through the reference snapshot's ``SymbolResolver``,
ADR 0018).

The last explore query over instruments: the single-instrument reads moved to the read model
(``services/read/instruments``, read-model PR 6); this module goes with the feature table in
read-model PR 7 (``docs/api/read-model.md``)."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pandas as pd

from algotrade.core.model.errors import ConfigurationError, MissingDataError
from algotrade.core.model.fields import REFERENCE_TABLE
from algotrade.data.prices import adjusted_bars
from algotrade.data.reference import instruments, resolver, snapshot
from algotrade.services.configs import catalog_of
from algotrade.services.explore.store import (
    BARS,
    NotFoundError,
    ReadStore,
    latest_session,
    partition_for,
    record,
    store_features,
)
from algotrade.services.features import field_view

DEFAULT_SPAN = timedelta(days=365)


def resolve_key(store: ReadStore, key: str, on: date | None = None) -> tuple[str, date]:
    """-> (instrument_id, the reference snapshot used: the one ``on`` sees, the earliest
    before the first). ``NotFoundError`` for an unknown id or ticker."""
    snap = snapshot(store.reader, REFERENCE_TABLE, on)
    if snap is None:
        raise NotFoundError(f"{REFERENCE_TABLE}: nothing stored")
    session = snap.snapshot_date
    if not instruments(store.reader, session, [key]).empty:
        return key, session
    names = resolver(store.reader, session)
    if names.knows(key):
        return names.id_for(key), session
    raise NotFoundError(f"no instrument {key!r} in the reference snapshot {session}")


def _span(store: ReadStore, start: date | None, end: date | None) -> tuple[date, date]:
    last = end or partition_for(store.reader, BARS, None)
    return start or last - DEFAULT_SPAN, last


MAX_COMPARE = 10


@dataclass(frozen=True)
class Compared:
    instrument_id: str
    symbol: str | None


def _resolve_many(store: ReadStore, keys: list[str], on: date | None) -> list[Compared]:
    if not keys or len(keys) > MAX_COMPARE:
        raise ConfigurationError(f"compare 1 to {MAX_COMPARE} instruments, got {len(keys)}")
    out = []
    for key in dict.fromkeys(keys):
        iid, session = resolve_key(store, key, on)
        out.append(Compared(iid, resolver(store.reader, session).symbol_for(iid)))
    return out


@dataclass(frozen=True)
class FeatureComparison:
    session: date
    instruments: list[Compared]
    missing: list[str]  # tables with no partition for the session (their rows are null)
    rows: list[dict[str, Any]]  # feature, dtype, values: {instrument_id: value}


def compare_features(
    store: ReadStore, keys: list[str], names: list[str] | None, on: date | None = None
) -> FeatureComparison:
    """One row per feature (every catalogue field by default), one value per instrument, for
    the session ``on`` (the latest session with bars by default)."""
    session = on or latest_session(store.reader)
    if session is None:
        raise NotFoundError("nothing stored")
    compared = _resolve_many(store, keys, session)
    fs = store_features(store)
    catalogue = catalog_of(fs)
    wanted = list(dict.fromkeys(names or catalogue.fields))
    for name in wanted:
        catalogue.check_field(name, "features")
    ids = [c.instrument_id for c in compared]
    view = field_view(store.reader, session, wanted, ids=ids, features=fs)
    by_id = {str(r["instrument_id"]): record(r) for r in view.frame.to_dict("records")}
    rows = [
        {
            "feature": name,
            "dtype": catalogue.fields[name],
            "values": {i: by_id.get(i, {}).get(name) for i in ids},
        }
        for name in wanted
    ]
    return FeatureComparison(session, compared, list(view.missing), rows)


@dataclass(frozen=True)
class PriceComparison:
    instruments: list[Compared]
    adjustment: str
    rebase: float | None  # each series divided by its first close, times this (None: raw)
    start: date
    end: date
    dates: list[date]  # the union of the instruments' sessions
    series: dict[str, list[float | None]]  # instrument_id -> close per date (None: no bar)


def compare_prices(
    store: ReadStore,
    keys: list[str],
    start: date | None,
    end: date | None,
    rebase: float | None = 100.0,
    adjustment: str = "splits",
) -> PriceComparison:
    """Daily closes of each instrument on one date axis, rebased to ``rebase`` at each
    series' first close (the last year of stored bars by default)."""
    compared = _resolve_many(store, keys, end)
    first, last = _span(store, start, end)
    ids = [c.instrument_id for c in compared]
    try:
        frame, _ = adjusted_bars(store.reader, "1d", first, last, ids, adjustment=adjustment)
    except MissingDataError:
        return PriceComparison(compared, adjustment, rebase, first, last, [], {i: [] for i in ids})
    closes = frame.pivot_table(
        index="session_date", columns="instrument_id", values="close", aggfunc="last"
    ).sort_index()
    if rebase:
        closes = closes / closes.bfill().iloc[0] * rebase
    closes = closes.reindex(columns=ids)
    series = {i: [None if pd.isna(v) else float(v) for v in closes[i]] for i in ids}
    return PriceComparison(compared, adjustment, rebase, first, last, list(closes.index), series)
