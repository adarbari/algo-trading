"""Snapshot tables (reference, company, universe, id map, IBKR contracts): ONE rule for the
snapshot read.

``snapshot(reader, table, on)`` is the latest partition on or before ``on``; when there is
none it falls back to the EARLIEST partition and says so (``pre_snapshot``). Reading a date
before the first snapshot therefore works, but uses a list of instruments taken later:
survivorship bias, which backtests record (ADR 0007, ADR 0019 R1). Everything here that
reads a snapshot table goes through ``snapshot``.

``instruments/description`` is the exception: it is stored in increments (each run adds the
descriptions it fetched), not as snapshots, so ``descriptions`` unions every partition and
keeps the latest stored row per instrument.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pandas as pd

from algotrade.core.model.errors import MissingDataError
from algotrade.core.model.fields import (
    COMPANY_TABLE,
    DESCRIPTION_TABLE,
    REFERENCE_TABLE,
    field_source,
    instrument_field,
)
from algotrade.core.model.instruments import AssetClass, Instrument
from algotrade.data.resolver import SymbolResolver
from algotrade.storage.tables.readers import StoreReader

UNIVERSE_TABLE = "universe"
IBKR_CONTRACTS = "instruments/ibkr_contracts"
UNIVERSE_HINT = "algotrade-ingest universe import --stocks <csv> --etfs <csv> --version <v>"
REFERENCE_HINT = "run the ingestion job that loads instrument reference data"


@dataclass(frozen=True)
class Snapshot:
    """The partition of a snapshot table that a read for ``on`` uses."""

    table: str
    snapshot_date: date
    on: date | None  # the date asked for; None = the latest snapshot

    @property
    def pre_snapshot(self) -> bool:
        """True when ``on`` is before the first snapshot and a later one stands in."""
        return self.on is not None and self.snapshot_date > self.on


def snapshot(reader: StoreReader, table: str, on: date | None = None) -> Snapshot | None:
    """Latest snapshot on or before ``on`` (any, when ``on`` is None), else the earliest.

    ``None`` only when the table has no partition at all."""
    dates = reader.dates(table)
    if not dates:
        return None
    before = [d for d in dates if on is None or d <= on]
    return Snapshot(table, before[-1] if before else dates[0], on)


def read_snapshot(
    reader: StoreReader,
    table: str,
    on: date | None,
    hint: str,
    as_of: datetime | None = None,
    instruments: Sequence[str] | None = None,
) -> tuple[pd.DataFrame, Snapshot]:
    """The rows of ``snapshot(table, on)``; ``MissingDataError`` when there is none."""
    snap = snapshot(reader, table, on)
    if snap is None:
        raise MissingDataError(table, "no snapshot stored" + (f" (for {on})" if on else ""), hint)
    frame = reader.table(table, snap.snapshot_date, as_of, instruments)
    if frame is None:
        raise MissingDataError(table, f"snapshot {snap.snapshot_date} not known at {as_of}", hint)
    return frame, snap


# ---------------------------------------------------------------------- instruments (L1)
def instruments(
    reader: StoreReader,
    on: date,
    ids: Sequence[str] | None = None,
    as_of: datetime | None = None,
) -> pd.DataFrame:
    """The ``instruments/reference`` snapshot for ``on`` (see ``snapshot``)."""
    return read_snapshot(reader, REFERENCE_TABLE, on, REFERENCE_HINT, as_of, ids)[0]


def companies(
    reader: StoreReader,
    on: date,
    ids: Sequence[str] | None = None,
    as_of: datetime | None = None,
) -> pd.DataFrame | None:
    """The ``instruments/company`` snapshot on or before ``on`` (``ids``' rows only when
    given); ``None`` when none was taken by then (a later snapshot never stands in for what a
    page shows: it would show company facts not known on ``on``)."""
    snap = snapshot(reader, COMPANY_TABLE, on)
    if snap is None or snap.pre_snapshot:
        return None
    return reader.table(COMPANY_TABLE, snap.snapshot_date, as_of, ids)


ALL_TIME = (date(1900, 1, 1), date(9999, 12, 31))
DESCRIPTION_COLUMNS = (
    "instrument_id",
    "symbol",
    "description",
    "description_source",
    "homepage_url",
    "total_employees",
    "filed",
    "accn",
    "fetched_on",
)


def stored_descriptions(
    reader: StoreReader, ids: Sequence[str] | None = None, as_of: datetime | None = None
) -> pd.DataFrame:
    """Every stored description row (``DESCRIPTION_COLUMNS``), the latest version per
    instrument, markers (no text: the vendor had none) included; empty when none. The
    ingestion task reads this to see what is already asked."""
    frame = reader.table_range(DESCRIPTION_TABLE, *ALL_TIME, as_of, ids)
    if frame is None or frame.empty:
        return pd.DataFrame(columns=list(DESCRIPTION_COLUMNS))
    frame = frame.sort_values("knowledge_ts", kind="stable")
    frame = frame.drop_duplicates("instrument_id", keep="last")
    frame = frame.reindex(columns=list(DESCRIPTION_COLUMNS))  # all-null columns may be absent
    for column in ("filed", "fetched_on"):
        day = pd.to_datetime(frame[column]).dt.date
        frame[column] = day.astype(object).where(frame[column].notna(), None)
    return frame.sort_values("instrument_id", kind="stable").reset_index(drop=True)


def descriptions(
    reader: StoreReader, ids: Sequence[str] | None = None, as_of: datetime | None = None
) -> pd.DataFrame:
    """The stored descriptions that have text, one row per instrument (``stored_descriptions``
    without the markers). What the Explore overview shows for a company or fund."""
    frame = stored_descriptions(reader, ids, as_of)
    return frame[frame["description"].notna()].reset_index(drop=True)


def ibkr_contracts(
    reader: StoreReader, on: date, as_of: datetime | None = None
) -> pd.DataFrame | None:
    """The ``instruments/ibkr_contracts`` snapshot on or before ``on`` (IBKR conid and primary
    exchange per instrument, ADR 0028); ``None`` when none was resolved by then (a later
    snapshot never stands in: it would claim contracts not known on ``on``)."""
    snap = snapshot(reader, IBKR_CONTRACTS, on)
    if snap is None or snap.pre_snapshot:
        return None
    return reader.table(IBKR_CONTRACTS, snap.snapshot_date, as_of)


def _present[T](value: object, default: T) -> T:
    """``default`` when a column is absent, None or NaN (Parquet fills gaps with NaN)."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return default
    return value  # type: ignore[return-value]


def instrument_terms(
    reader: StoreReader,
    on: date,
    ids: Sequence[str] | None = None,
    as_of: datetime | None = None,
) -> dict[str, Instrument]:
    """Contract terms (multiplier, tick size, asset class) for engines."""
    frame = instruments(reader, on, ids, as_of)
    return {
        str(r.instrument_id): Instrument(
            instrument_id=str(r.instrument_id),
            symbol=str(r.symbol),
            asset_class=AssetClass(str(r.asset_class)),
            multiplier=float(r.multiplier),  # type: ignore[arg-type]
            currency=str(_present(getattr(r, "currency", None), "USD")),
            tick_size=float(_present(getattr(r, "tick_size", None), 0.01)),
        )
        for r in frame.itertuples(index=False)
    }


def resolver(reader: StoreReader, on: date, as_of: datetime | None = None) -> SymbolResolver:
    """Symbol -> instrument id for ``on`` (ADR 0018). Empty store: symbol ids."""
    snap = snapshot(reader, REFERENCE_TABLE, on)
    if snap is None:
        return SymbolResolver()
    frame = reader.table(REFERENCE_TABLE, snap.snapshot_date, as_of)
    return SymbolResolver.from_reference(frame, snap.snapshot_date)


def symbol_ids(reader: StoreReader, on: date) -> pd.DataFrame | None:
    """``symbol``, ``instrument_id`` (one row per ticker, sorted by symbol) and
    ``pre_snapshot`` from the reference snapshot ``on`` sees, as ``resolver`` resolves them:
    how a market-entity feature group finds SPY's id without building it (ADR 0047, ADR
    0018). ``None`` when no reference is stored."""
    found = resolver(reader, on)
    if found.snapshot is None or not found.ids:
        return None
    frame = pd.DataFrame(sorted(found.ids.items()), columns=["symbol", "instrument_id"])
    return frame.assign(pre_snapshot=found.snapshot > on)


def ids_for_symbols(
    reader: StoreReader, sessions: Sequence[date], symbols: Sequence[str]
) -> list[str]:
    """The ids ``symbols`` resolve to in the reference snapshot each of ``sessions`` sees, as
    ``symbol_ids`` resolves them (each snapshot read once), as one sorted union: a superset of
    any one session's ids, to narrow a read (``Input.symbols``, ADR 0047). Empty when no
    reference is stored or none of the symbols is listed."""
    found: set[str] = set()
    seen: set[date] = set()
    for day in sessions:
        snap = snapshot(reader, REFERENCE_TABLE, day)
        if snap is None:
            return []
        if snap.snapshot_date in seen:
            continue
        seen.add(snap.snapshot_date)
        ids = resolver(reader, day).ids
        found |= {ids[s] for s in symbols if s in ids}
    return sorted(found)


@dataclass(frozen=True)
class InstrumentView:
    """L1 for one date: reference facts + rollups, one row per instrument (ADR 0016).

    Columns are field names (``instrument.<col>``, ``rollup.<name>@vN.<col>``) plus
    ``instrument_id``. A rollup with no partition for ``session`` is listed in ``missing``
    and its fields are absent, which selections treat as UNKNOWN (never as a pass).
    ``pre_snapshot``: the reference came from a snapshot after ``session`` (survivorship);
    ``company_pre_snapshot``: so did the company facts.
    """

    session: date
    reference_snapshot: date
    frame: pd.DataFrame
    missing: tuple[str, ...]
    pre_snapshot: bool = False
    company_pre_snapshot: bool = False


def join_fields(
    out: pd.DataFrame, frame: pd.DataFrame, columns: Sequence[tuple[str, str]]
) -> pd.DataFrame:
    """``out`` left-joined on ``instrument_id`` with ``frame``'s ``(field, column)`` pairs,
    each as its field name (a column ``frame`` lacks is left out)."""
    # Build the joined columns by name so the join key itself is never renamed.
    picked = pd.DataFrame({"instrument_id": frame["instrument_id"].astype(str)})
    for name, column in columns:
        if column in frame.columns:
            picked[name] = frame[column].to_numpy()
    return out.merge(picked, on="instrument_id", how="left")


def instrument_view(
    reader: StoreReader,
    session: date,
    fields: Sequence[str] | None = None,
    ids: Sequence[str] | None = None,
    as_of: datetime | None = None,
) -> InstrumentView:
    """Reference snapshot for ``session`` joined with rollups *for* ``session``.

    Company fields (``instrument.sector``…) come from the ``instruments/company`` snapshot
    for ``session`` (same rule); without one they are ``missing`` (UNKNOWN). ``fields``
    limits the columns (and the rollup tables read); ``None`` means every reference column
    and no rollups.
    """
    reference, ref = read_snapshot(reader, REFERENCE_TABLE, session, REFERENCE_HINT, as_of, ids)
    wanted: dict[str, list[tuple[str, str]]] = {}
    for name in fields if fields is not None else [instrument_field(str(c)) for c in reference]:
        table, column = field_source(name)
        wanted.setdefault(table, []).append((name, column))
    out = pd.DataFrame({"instrument_id": reference["instrument_id"].astype(str)})
    missing: list[str] = []
    company_pre = False
    for table, columns in wanted.items():
        if table == REFERENCE_TABLE:
            frame: pd.DataFrame | None = reference
        elif table == COMPANY_TABLE:  # a snapshot table, like the reference
            company = snapshot(reader, table, session)
            frame = reader.table(table, company.snapshot_date, as_of) if company else None
            company_pre = company is not None and company.pre_snapshot
        else:
            frame = reader.table(table, session, as_of)
        if frame is None:
            missing.append(table)
            continue
        out = join_fields(out, frame, columns)
    return InstrumentView(
        session, ref.snapshot_date, out, tuple(sorted(missing)), ref.pre_snapshot, company_pre
    )


# ---------------------------------------------------------------------- universe
@dataclass(frozen=True)
class Universe:
    snapshot_date: date
    frame: pd.DataFrame  # every covered instrument; strategies narrow it with selections
    rows_loaded: int
    version: str
    last_verified: date | None
    pre_snapshot: bool = False  # the snapshot is after the session asked for (survivorship)

    @property
    def instruments(self) -> list[str]:
        return list(self.frame["instrument_id"])

    def is_stale(self, session_date: date, max_age_days: int) -> bool:
        reference = self.last_verified or self.snapshot_date
        return session_date - reference > timedelta(days=max_age_days)


def load_universe(
    reader: StoreReader, session_date: date, as_of: datetime | None = None
) -> Universe:
    frame, snap = read_snapshot(reader, UNIVERSE_TABLE, session_date, UNIVERSE_HINT, as_of)
    raw_verified = frame["last_verified"] if "last_verified" in frame else pd.Series(dtype=str)
    verified = pd.to_datetime(raw_verified, errors="coerce").dropna()
    return Universe(
        snapshot_date=snap.snapshot_date,
        frame=frame.reset_index(drop=True),
        rows_loaded=len(frame),
        version=str(frame["universe_version"].iloc[0]) if len(frame) else "",
        # Oldest verification date: the conservative reading when rows disagree (fail closed).
        last_verified=verified.min().date() if len(verified) else None,
        pre_snapshot=snap.pre_snapshot,
    )
