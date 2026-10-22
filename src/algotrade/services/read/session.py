"""Which session a read serves (ADR 0036): ``resolve_session`` turns the date asked for (or
none) into one ``Session``, and ``grain_of`` says how a table is read for it.

Requested given: that date, even if nothing is stored for it (every value is then UNKNOWN).
None: the latest session whose nightly workflow is complete (ADR 0062: a ``nightly``
run record is done by ``storage.runs.done_sessions``, the rule the ingestion planner uses:
COMPLETE, a waived step included, or PARTIAL from before ADR 0039; and it has a ``bars/1d``
partition); the newer sessions still processing or failing are disclosed (``Session.newer``),
never mixed in. No session complete yet (an empty run history): the latest ``bars/1d``
partition (flagged: ``complete`` is False); no bars: the latest reference snapshot; an empty
store: ``NotFoundError``. Session-grain tables are then read for exactly ``Session.date``
(``context.partition``); snapshot tables follow ADR 0007's one rule (``data.reference.snapshot``)
and the ``Session`` discloses the reference snapshot used. This module is the only place the
grain of a table decides anything (docs/api/read-model.md "Session resolution")."""

import datetime as dt
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from algotrade.core.model.errors import AlgoTradeError
from algotrade.core.model.fields import COMPANY_TABLE, DESCRIPTION_TABLE, REFERENCE_TABLE
from algotrade.data import StoreReader
from algotrade.data.funds.holdings import TABLE as HOLDINGS_TABLE
from algotrade.data.reference import IBKR_CONTRACTS, UNIVERSE_TABLE, snapshot
from algotrade.services.read.availability.cause import Unavailable, UnavailableKind
from algotrade.services.read.availability.unavailable import unavailable_tables
from algotrade.storage.runs import RunRecord, RunStatus, done_sessions, published
from algotrade.storage.tables.spec import SCHEMA_VERSION

BARS = "bars/1d"
NIGHTLY = "nightly"  # the job name of the nightly workflow's per-session run records
# The post-session workflow's records (ADR 0070): descriptions, verify, edge-eval. Never read for
# completeness or the cutoff (ADR 0062 reads ``NIGHTLY`` alone); only to explain a gap, for Admin.
POST_SESSION = "post-session"
# The architecture registry at the repo root (the workspace installs this package editable).
TABLES = Path(__file__).resolve().parents[4] / "architecture" / "tables.toml"


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
    ("rollups/market/", Grain.SESSION),  # market-entity groups: the MKT:US row (ADR 0047)
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
# (architecture/tables.toml) under rollups/instrument/, chains/ and results/, plus bars/1d.
# verification/* and live/* are not produced nightly and are never listed, nor is an entry with
# ``per_session = false`` (results/edge_eval: partitioned by an evaluation's range end). Read once.
_NIGHTLY_PREFIXES = ("rollups/instrument/", "chains/", "results/")


def expected_tables(tables: Path = TABLES) -> tuple[str, ...]:
    """The session-grain tables a complete session has, sorted (wildcard entries such as
    ``results/*`` name a family, not a table, and are skipped; so are ``per_session = false``
    entries)."""
    declared = tomllib.loads(tables.read_text())["table"]
    names = {
        t["name"]
        for t in declared
        if t["name"].startswith(_NIGHTLY_PREFIXES) and t.get("per_session", True)
    }
    return tuple(sorted({n for n in names if "*" not in n} | {BARS}))


EXPECTED_TABLES = expected_tables()


class NewerState(StrEnum):
    """What a session newer than the one served is doing (ADR 0062)."""

    IN_PROGRESS = "IN_PROGRESS"  # bars or a run record exist: running, or waiting for a source
    FAILED_RETRYING = "FAILED_RETRYING"  # a critical step failed; the hourly nightly retries it
    # complete, but the serving release that makes it the default is not promoted yet (ADR 0077
    # decision 7); disclosed only once the configured delay has passed since it completed
    PUBLISHING = "PUBLISHING"


Due = tuple[dt.date, dt.datetime]  # (the newer complete session, when it is to be disclosed)
_UNREAD: Any = object()  # "not read yet" for ``resolve_session`` (``None`` is a real answer)


def publishing_due(reader: StoreReader, day: dt.date, delay: dt.timedelta) -> Due | None:
    """The newest complete session after ``day`` (a nightly done by ``done_sessions`` and with
    bars, as ``completeness`` counts it) and the instant it is disclosed as publishing: ``delay``
    after the run that completed it finished. ``None``: no such session. Reads the run records
    (and the bar days): the caller keeps the answer (``context._session`` does, per runs
    generation) instead of asking per request."""
    records = reader.runs(NIGHTLY)
    newer = sorted(d for d in done_sessions(records) & set(reader.dates(BARS)) if d > day)
    if not newer:
        return None
    finished = session_cutoff(records, newer[-1])
    return None if finished is None else (newer[-1], finished + delay)


@dataclass(frozen=True)
class Serving:
    """The serving release the default session follows (ADR 0077 decision 7): ``session`` is the
    release's, ``now`` the request's clock (read once per request) and ``publishing_delay`` how
    long a newer session may be complete before it is disclosed as ``PUBLISHING``."""

    session: dt.date
    now: dt.datetime
    publishing_delay: dt.timedelta

    def key(self, due: Due | None) -> tuple[dt.date, bool]:
        """What a cached ``Session`` under this serving depends on besides the store: the day and
        whether the instant the newer session is disclosed has passed (the flag flips the cached
        answer, so a client never supplies the clock)."""
        return self.session, due is not None and self.now >= due[1]

    def publishing(self, due: Due | None) -> "NewerSession | None":
        """The complete session after ``session``, once its disclosure instant has passed."""
        if due is None or self.now < due[1]:
            return None
        return NewerSession(due[0], NewerState.PUBLISHING)


@dataclass(frozen=True)
class NewerSession:
    """The newest session after the one served whose nightly workflow is not complete: its
    ``date``, its ``state`` and, when a step failed, the public ``kind`` of the failure (never
    the step, table or error: ADR 0056)."""

    date: dt.date
    state: NewerState
    kind: UnavailableKind | None = None


@dataclass(frozen=True)
class Session:
    """The one session a read serves, and what is stored for it.

    ``requested`` is the date asked for (None: the latest); ``latest_with_bars`` the latest
    ``bars/1d`` partition (None: no bars); ``is_latest`` whether ``date`` is what a read with no
    date resolves to. ``reference_snapshot`` is the ``instruments/reference`` partition identity
    is read from (None: none stored) and ``pre_snapshot`` whether it is later than ``date``
    (survivorship, ADR 0007). ``present`` / ``missing``: the expected session-grain tables with
    and without a partition for ``date``; ``unavailable``: what the ``missing`` ones leave out,
    in public words (ADR 0056). ``complete``: the nightly workflow of ``date`` is complete (False
    for an explicit date that is not, and for the fallback of a store with no complete session);
    ``newer``: the incomplete session after ``date`` a default read leaves out (ADR 0062).
    ``cutoff``: when the nightly of ``date`` FIRST completed (the finish time of its first
    published record, the test ``done_sessions`` uses; ADR 0064 decision 9 amendment): rows with a
    later ``knowledge_ts`` are not what the session knew. None: it has not completed."""

    date: dt.date
    requested: dt.date | None
    is_latest: bool
    latest_with_bars: dt.date | None
    reference_snapshot: dt.date | None
    pre_snapshot: bool
    present: tuple[str, ...]
    missing: tuple[str, ...]
    unavailable: tuple[Unavailable, ...] = ()
    complete: bool = False
    newer: NewerSession | None = None
    cutoff: dt.datetime | None = None


def reference_snapshot_on(reader: StoreReader, day: dt.date) -> dt.date | None:
    """The ``instruments/reference`` snapshot in force on ``day`` (ADR 0007's one rule: the latest
    on or before it, the earliest before every snapshot); None: none stored. For a read of a
    PAST day inside a page of one session (a trade's ticker at its decision session)."""
    found = snapshot(reader, REFERENCE_TABLE, day)
    return None if found is None else found.snapshot_date


def reference_snapshots(reader: StoreReader) -> list[dt.date]:
    """The dates of every stored ``instruments/reference`` snapshot, oldest first."""
    return sorted(reader.dates(REFERENCE_TABLE))


def session_cutoff(records: Sequence[RunRecord], day: dt.date) -> dt.datetime | None:
    """The finish time of the first published ``nightly`` record of ``day`` (None: none)."""
    done = [
        r.finished_at
        for r in records
        if r.session_date == day and published(r) and r.finished_at is not None
    ]
    return min(done) if done else None


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


def _nightly_by_session(reader: StoreReader) -> dict[dt.date, RunRecord]:
    """Each session's latest ``nightly`` run record (by start time)."""
    latest: dict[dt.date, RunRecord] = {}
    for record in reader.runs(NIGHTLY):
        held = latest.get(record.session_date)
        if held is None or record.started_at > held.started_at:
            latest[record.session_date] = record
    return latest


def _newer(day: dt.date, record: RunRecord | None) -> NewerSession:
    if record is not None and record.status is RunStatus.FAILED:
        return NewerSession(day, NewerState.FAILED_RETRYING, UnavailableKind.SYSTEM)
    return NewerSession(day, NewerState.IN_PROGRESS)


@dataclass(frozen=True)
class Completeness:
    """What the nightly's run records say about the sessions with bars: ``complete`` (the done
    ones, by ``storage.runs.done_sessions``), ``last`` the latest of them (None: none) and
    ``newer`` the newest session after it that is not (it has bars or a record)."""

    complete: frozenset[dt.date]
    last: dt.date | None
    newer: NewerSession | None


def completeness(reader: StoreReader) -> Completeness:
    """The sessions whose nightly workflow is complete (ADR 0062): done by the one rule the
    ingestion planner uses (any record COMPLETE, a waived step included, or PARTIAL from before
    ADR 0039) and with a ``bars/1d`` partition; FAILED, WAITING and running ones are not."""
    records = reader.runs(NIGHTLY)
    bar_days = set(reader.dates(BARS))
    done = frozenset(done_sessions(records) & bar_days)
    if not done:
        return Completeness(done, None, None)
    last = max(done)
    latest: dict[dt.date, RunRecord] = {}
    for record in records:
        held = latest.get(record.session_date)
        if held is None or record.started_at > held.started_at:
            latest[record.session_date] = record
    later = sorted(d for d in bar_days | set(latest) if d > last)
    return Completeness(done, last, _newer(later[-1], latest.get(later[-1])) if later else None)


def _after_release(found: Completeness, serving: Serving, due: Due | None) -> NewerSession | None:
    """What is newer than the released session: a complete one (``PUBLISHING`` after the delay),
    else what ``completeness`` says is still processing or failing after the newest complete."""
    if found.last is not None and found.last > serving.session:
        return serving.publishing(due)
    return found.newer


def default_session(reader: StoreReader) -> dt.date | None:
    """The session a read or an on-request run with no date serves: the latest complete one
    (ADR 0062); none complete: the latest ``bars/1d`` partition, else the latest reference
    snapshot; None on an empty store. The one default, beside ``resolve_session``."""
    return completeness(reader).last or latest_session(reader)


def resolve_session(
    reader: StoreReader,
    requested: dt.date | None,
    expected: Sequence[str] = EXPECTED_TABLES,
    serving: Serving | None = None,
    due: Due | None = _UNREAD,
) -> Session:
    """The session a read for ``requested`` serves (see the module docstring). ``expected``:
    the session-grain tables checked for ``present`` / ``missing`` (tests pass their own).
    ``serving``: a read with no date serves the serving release's session, not the newest complete
    one (ADR 0077 decision 7): a newer complete session is ``newer`` as ``PUBLISHING`` once the
    delay has passed, one still processing or failing as before; ``None``: ADR 0062 unchanged."""
    bars = snapshot(reader, BARS)
    found = completeness(reader)
    default = found.last or latest_session(reader)
    newer = found.newer
    if serving is not None and requested is None:
        default = serving.session
        if due is _UNREAD:
            due = publishing_due(reader, serving.session, serving.publishing_delay)
        newer = _after_release(found, serving, due)
    if requested is not None:
        day, newer = requested, None
    elif default is not None:
        day = default
    else:
        raise NotFoundError("nothing stored: no bars/1d and no instruments/reference partition")
    reference = snapshot(reader, REFERENCE_TABLE, day)
    present = tuple(t for t in expected if reader.has_partition(t, day))
    missing = tuple(t for t in expected if t not in present)
    return Session(
        date=day,
        requested=requested,
        is_latest=day == default,
        latest_with_bars=bars.snapshot_date if bars else None,
        reference_snapshot=reference.snapshot_date if reference else None,
        pre_snapshot=reference.pre_snapshot if reference else False,
        present=present,
        missing=missing,
        unavailable=unavailable_tables(missing, day),
        complete=day in found.complete,
        newer=newer,
        cutoff=session_cutoff(reader.runs(NIGHTLY), day),
    )
