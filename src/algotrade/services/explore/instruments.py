"""One instrument: reference + company + latest features, bars, events and feature series;
and several side by side (Explore compare: features and rebased prices).

``key`` is an ``instrument_id`` or a ticker (resolved through the reference snapshot's
``SymbolResolver``, ADR 0018), so a page can link by either.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pandas as pd

from algotrade.core.model.errors import ConfigurationError, MissingDataError
from algotrade.core.model.fields import (
    COMPANY_TABLE,
    FEATURE_FIELD_PREFIX,
    REFERENCE_TABLE,
    field_source,
    is_feature_field,
    rollup_field,
)
from algotrade.data.events import ALL_TIME, read_events
from algotrade.data.prices import adjusted_bars
from algotrade.data.reference import (
    instruments,
    read_snapshot,
    resolver,
    snapshot,
)
from algotrade.data.rollups import rollup_row, rollup_rows
from algotrade.features.registry import GROUPS
from algotrade.services.configs import field_catalog
from algotrade.services.explore.store import (
    BARS,
    NotFoundError,
    ReadStore,
    latest_session,
    partition_for,
    record,
    records,
)
from algotrade.services.features import field_view, read_expressions, site_features

DEFAULT_SPAN = timedelta(days=365)
EVENTS_PREFIX = "events/"


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


@dataclass(frozen=True)
class InstrumentDetail:
    instrument_id: str
    reference_snapshot: date
    reference: dict[str, Any]
    company: dict[str, Any] | None
    features: dict[str, Any]  # field name (rollup.<key>.<column>, feature.<name>) -> value
    feature_sessions: dict[str, date]  # rollup key (or "expressions") -> its values' session


def instrument_detail(store: ReadStore, key: str, on: date | None = None) -> InstrumentDetail:
    iid, session = resolve_key(store, key, on)
    reference = record(instruments(store.reader, session, [iid]).iloc[0])
    try:
        company_rows, _ = read_snapshot(store.reader, COMPANY_TABLE, session, "", None, [iid])
        company = record(company_rows.iloc[0]) if len(company_rows) else None
    except MissingDataError:
        company = None
    features: dict[str, Any] = {}
    sessions: dict[str, date] = {}
    for rollup_key, rollup in GROUPS.items():
        found = rollup_row(store.reader, rollup.table, iid, on)
        if found is None:
            continue
        sessions[rollup_key] = found[0]
        values = record(found[1], ["instrument_id"])
        features.update({rollup_field(rollup_key, c): v for c, v in values.items()})
    if sessions:  # expression features, on the latest session any group has for it
        latest = max(sessions.values())
        names = list(site_features().expressions)
        rows = read_expressions(store.reader, names, latest, instruments=[iid]).frame
        if len(rows):
            values = record(rows.iloc[0], ["instrument_id", "session_date"])
            features.update({f"{FEATURE_FIELD_PREFIX}{n}": values.get(n) for n in names})
            sessions["expressions"] = latest
    return InstrumentDetail(iid, session, reference, company, features, sessions)


@dataclass(frozen=True)
class BarSeries:
    instrument_id: str
    adjustment: str
    start: date
    end: date
    items: list[dict[str, Any]]  # ts, session_date, open, high, low, close, volume (+ vwap)


def _span(store: ReadStore, start: date | None, end: date | None) -> tuple[date, date]:
    last = end or partition_for(store.reader, BARS, None)
    return start or last - DEFAULT_SPAN, last


def instrument_bars(
    store: ReadStore, key: str, start: date | None, end: date | None, adjustment: str
) -> BarSeries:
    """Daily bars for ``start..end`` (the last year of stored bars by default), adjusted."""
    iid, _ = resolve_key(store, key, end)
    first, last = _span(store, start, end)
    try:
        frame, _ = adjusted_bars(store.reader, "1d", first, last, [iid], adjustment=adjustment)
    except MissingDataError:
        return BarSeries(iid, adjustment, first, last, [])
    columns = ["ts", "open", "high", "low", "close", "volume", "vwap"]
    rows = records(frame.reindex(columns=[*columns, "session_date"]).dropna(axis=1, how="all"))
    for row, day in zip(rows, frame["session_date"], strict=True):
        row["session_date"] = day
    return BarSeries(iid, adjustment, first, last, rows)


@dataclass(frozen=True)
class InstrumentEvent:
    table: str  # events/<kind>
    ts: str
    values: dict[str, Any]


def instrument_events(
    store: ReadStore, key: str, start: date | None, end: date | None
) -> list[InstrumentEvent]:
    """Every stored event of the instrument with event date in ``start..end`` (all time by
    default), from every ``events/*`` table, sorted by date."""
    iid, _ = resolve_key(store, key)
    first, last = start or ALL_TIME[0], end or ALL_TIME[1]
    out: list[InstrumentEvent] = []
    for table in store.reader.table_names():
        if not table.startswith(EVENTS_PREFIX):
            continue
        frame = read_events(store.reader, table, first, last, [iid]).frame
        for row in records(frame, ["instrument_id"]):
            out.append(InstrumentEvent(table, str(row.pop("ts")), row))
    return sorted(out, key=lambda e: (e.ts, e.table))


@dataclass(frozen=True)
class FeatureSeries:
    instrument_id: str
    names: list[str]
    start: date
    end: date
    items: list[dict[str, Any]]  # session_date + one key per feature name (null: UNKNOWN)


def _rollup_fields(names: list[str] | None) -> dict[str, list[tuple[str, str]]]:
    """Rollup table -> [(field name, column)] (``""``: expression features, by name); every
    rollup column and expression feature when ``names`` is None."""
    wanted = names or [
        *(rollup_field(k, c) for k, r in GROUPS.items() for c in r.columns),
        *(f"{FEATURE_FIELD_PREFIX}{n}" for n in site_features().expressions),
    ]
    known = field_catalog().fields
    tables: dict[str, list[tuple[str, str]]] = {}
    for name in wanted:
        if name not in known:
            raise NotFoundError(f"no feature {name!r} (GET /features lists them)")
        if is_feature_field(name):
            tables.setdefault("", []).append((name, name.removeprefix(FEATURE_FIELD_PREFIX)))
            continue
        table, column = field_source(name)
        if table in (REFERENCE_TABLE, COMPANY_TABLE):
            raise NotFoundError(f"{name}: a reference field has no time series")
        tables.setdefault(table, []).append((name, column))
    return tables


def instrument_features(
    store: ReadStore, key: str, names: list[str] | None, start: date | None, end: date | None
) -> FeatureSeries:
    """Feature values per session for ``start..end`` (the last year by default)."""
    iid, _ = resolve_key(store, key, end)
    first, last = _span(store, start, end)
    tables = _rollup_fields(names)
    by_day: dict[date, dict[str, Any]] = {}
    for table, fields in tables.items():
        if table:
            frame = rollup_rows(store.reader, table, first, last, instruments=[iid])
        else:
            computed = [column for _, column in fields]
            frame = read_expressions(store.reader, computed, first, last, instruments=[iid]).frame
        if frame is None:
            continue
        for row in frame.to_dict("records"):
            values = record(row)
            by_day.setdefault(row["session_date"], {}).update(
                {name: values.get(column) for name, column in fields}
            )
    ordered = [n for fields in tables.values() for n, _ in fields]
    items = [{"session_date": d, **by_day[d]} for d in sorted(by_day)]
    return FeatureSeries(iid, ordered, first, last, items)


# ---------------------------------------------------------------------- compare (Explore)
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
    catalogue = field_catalog()
    wanted = list(dict.fromkeys(names or catalogue.fields))
    for name in wanted:
        catalogue.check_field(name, "features")
    ids = [c.instrument_id for c in compared]
    view = field_view(store.reader, session, wanted, ids=ids)
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
