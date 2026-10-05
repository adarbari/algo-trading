"""Which session a read serves (ADR 0036): ``resolve_session`` turns the date asked for (or
none) into one ``Session``, and ``grain_of`` says how a table is read for it.

Requested given: that date, even if nothing is stored for it (every value is then UNKNOWN).
None: the latest ``bars/1d`` partition; no bars: the latest reference snapshot; an empty store:
``NotFoundError``. Session-grain tables are then read for exactly ``Session.date``
(``context.partition``); snapshot tables follow ADR 0007's one rule (``data.reference.snapshot``)
and the ``Session`` discloses the reference snapshot used. This module is the only place the
grain of a table decides anything (docs/api/read-model.md "Session resolution")."""

import datetime as dt
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from algotrade.core.model.errors import AlgoTradeError
from algotrade.core.model.fields import COMPANY_TABLE, DESCRIPTION_TABLE, REFERENCE_TABLE
from algotrade.data import StoreReader
from algotrade.data.funds.holdings import TABLE as HOLDINGS_TABLE
from algotrade.data.reference import IBKR_CONTRACTS, UNIVERSE_TABLE, snapshot
from algotrade.storage.tables.schemas import SCHEMA_VERSION

BARS = "bars/1d"
# The architecture registry at the repo root (the workspace installs this package editable).
OWNERSHIP = Path(__file__).resolve().parents[4] / "architecture" / "ownership.toml"


class NotFoundError(AlgoTradeError):
    """The thing asked for (an instrument, a run, a config, a partition) does not exist.
    Imported as ``services.read.context.NotFoundError`` (defined here, where the empty store
    raises it, so ``context`` can import this module without a cycle)."""


class Grain(StrEnum):
    """How a table is read for a session (docs/api/read-model.md, "Rules by table grain")."""

    SESSION = "session"  # exactly Session.date; absent -> Unknown(NO_PARTITION)
    SNAPSHOT = "snapshot"  # data.reference.snapshot (latest on or before, else pre_snapshot)
    EVENT = "event"  # by event date (ADR 0007), never by partition
    ISSUER_DATED = "issuer-dated"  # latest as_of on or before the date with filed <= date
    INCREMENTAL = "incremental"  # the latest stored row per instrument


# (table name or prefix ending in "/", grain); the first match wins.
GRAINS: tuple[tuple[str, Grain], ...] = (
    ("rollups/instrument/", Grain.SESSION),
    ("chains/", Grain.SESSION),
    ("results/", Grain.SESSION),
    (BARS, Grain.SESSION),
    ("verification/", Grain.SESSION),
    ("live/", Grain.SESSION),
    (REFERENCE_TABLE, Grain.SNAPSHOT),
    (COMPANY_TABLE, Grain.SNAPSHOT),
    (UNIVERSE_TABLE, Grain.SNAPSHOT),
    ("instruments/id_map", Grain.SNAPSHOT),
    (IBKR_CONTRACTS, Grain.SNAPSHOT),
    ("events/", Grain.EVENT),
    (HOLDINGS_TABLE, Grain.ISSUER_DATED),
    (DESCRIPTION_TABLE, Grain.INCREMENTAL),
)


def grain_of(table: str) -> Grain:
    """The grain ``table`` is read by; ``ValueError`` for a table with no declared grain (a
    read model reading it first declares it here, in docs/api/read-model.md)."""
    for key, grain in GRAINS:
        if table == key or (key.endswith("/") and table.startswith(key)):
            return grain
    raise ValueError(f"{table}: no read grain declared (docs/api/read-model.md, table grain)")


# Session-grain tables expected for every session: the declared ``[[table]]`` entries
# (architecture/ownership.toml) under rollups/instrument/, chains/ and results/, plus bars/1d.
# verification/* and live/* are not produced nightly and are never listed. Read once.
_NIGHTLY_PREFIXES = ("rollups/instrument/", "chains/", "results/")


def expected_tables(ownership: Path = OWNERSHIP) -> tuple[str, ...]:
    """The session-grain tables a complete session has, sorted (wildcard entries such as
    ``results/*`` name a family, not a table, and are skipped)."""
    declared = tomllib.loads(ownership.read_text())["table"]
    names = {t["name"] for t in declared if t["name"].startswith(_NIGHTLY_PREFIXES)}
    return tuple(sorted({n for n in names if "*" not in n} | {BARS}))


EXPECTED_TABLES = expected_tables()


@dataclass(frozen=True)
class Session:
    """The one session a read serves, and what is stored for it.

    ``requested`` is the date asked for (None: the latest); ``latest_with_bars`` the latest
    ``bars/1d`` partition (None: no bars); ``is_latest`` whether ``date`` is what a read with no
    date resolves to. ``reference_snapshot`` is the ``instruments/reference`` partition identity
    is read from (None: none stored) and ``pre_snapshot`` whether it is later than ``date``
    (survivorship, ADR 0007). ``present`` / ``missing``: the expected session-grain tables with
    and without a partition for ``date``."""

    date: dt.date
    requested: dt.date | None
    is_latest: bool
    latest_with_bars: dt.date | None
    reference_snapshot: dt.date | None
    pre_snapshot: bool
    present: tuple[str, ...]
    missing: tuple[str, ...]


def latest_session(reader: StoreReader) -> dt.date | None:
    """The session a read with no date serves: the latest ``bars/1d`` partition, else the
    latest reference snapshot; None on an empty store. For what is not a page read: the
    on-request runner's target session (ADR 0033), ``store_info``, ``make status``."""
    latest = snapshot(reader, BARS) or snapshot(reader, REFERENCE_TABLE)
    return latest.snapshot_date if latest is not None else None


@dataclass(frozen=True)
class StoreInfo:
    """How fresh the store is (``GET /health``): the latest session (None: empty), the
    stored tables and the storage schema version."""

    latest_session: dt.date | None
    tables: tuple[str, ...]
    schema_version: str


def store_info(reader: StoreReader) -> StoreInfo:
    """The latest session, the stored tables and the schema version of ``reader``'s store."""
    return StoreInfo(latest_session(reader), tuple(reader.table_names()), str(SCHEMA_VERSION))


def resolve_session(
    reader: StoreReader, requested: dt.date | None, expected: Sequence[str] = EXPECTED_TABLES
) -> Session:
    """The session a read for ``requested`` serves (see the module docstring). ``expected``:
    the session-grain tables checked for ``present`` / ``missing`` (tests pass their own)."""
    bars = snapshot(reader, BARS)
    latest_reference = snapshot(reader, REFERENCE_TABLE)
    latest = bars or latest_reference
    if requested is not None:
        day = requested
    elif latest is not None:
        day = latest.snapshot_date
    else:
        raise NotFoundError("nothing stored: no bars/1d and no instruments/reference partition")
    reference = snapshot(reader, REFERENCE_TABLE, day)
    present = tuple(t for t in expected if day in reader.dates(t))
    return Session(
        date=day,
        requested=requested,
        is_latest=latest is not None and day == latest.snapshot_date,
        latest_with_bars=bars.snapshot_date if bars else None,
        reference_snapshot=reference.snapshot_date if reference else None,
        pre_snapshot=reference.pre_snapshot if reference else False,
        present=present,
        missing=tuple(t for t in expected if t not in present),
    )
