"""Ingestion completeness for the Admin pages: per dataset and session, the rows stored against
the rows expected (``Completeness``, the window of sessions ending at ``ctx.session.date``), and
one cell with the reasons behind it (``CellDetail``: item statuses grouped by reason, the runs
that wrote it).

An inventory of what is stored, not a fact for a session: it reads partitions on the sessions
of the window it names through the context's inventory reads (``stored_dates``,
``partition_on``, ``snapshot_on``). Expected rows, per kind of dataset:

- ``session`` (bars, rollups): the rows of the dataset's previous stored session (a drop is the
  signal, as the quality checks use it); COMPLETE at 98% or more, PARTIAL below, MISSING
  without a partition.
- ``chains``: underlyings whose chain fetch is ``OK`` (``chains/status``) against the
  optionable instruments of the universe snapshot the session sees.
- ``snapshot`` (reference, universe): COMPLETE when a snapshot was built that session, CARRIED
  when an earlier one stands in, MISSING before the first."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from algotrade.core.model.errors import MissingDataError
from algotrade.core.time.calendar import last_closed_session, sessions_ending
from algotrade.data.chains import CHAIN_STATUS, OPTION_QUOTES
from algotrade.data.reference import UNIVERSE_TABLE, load_universe
from algotrade.features.registry import GROUPS
from algotrade.services.read.context import (
    ReadContext,
    Stores,
    partition,
    partition_on,
    snapshot_on,
    stored_dates,
)
from algotrade.services.read.ops.runs import FailureGroup, RunDetail, failure_groups, run_detail
from algotrade.services.read.values import Unknown

COMPLETE_SHARE = 0.98
MAX_SESSIONS = 60


@dataclass(frozen=True)
class Dataset:
    name: str  # the table (chains: the option quotes the status describes)
    job: str  # the run-record job of the ingestion task that writes it
    kind: str  # session | chains | snapshot


DATASETS: tuple[Dataset, ...] = (
    Dataset("instruments/reference", "universe_build", "snapshot"),
    Dataset(UNIVERSE_TABLE, "universe_build", "snapshot"),
    Dataset("bars/1d", "daily_bars", "session"),
    Dataset(OPTION_QUOTES, "option_chains", "chains"),
    *(Dataset(r.table, "rollups", "session") for r in GROUPS.values()),
)
BY_NAME = {d.name: d for d in DATASETS}


@dataclass(frozen=True)
class Cell:
    """One dataset on one session: ``status`` COMPLETE, PARTIAL, MISSING or CARRIED;
    ``basis`` what ``expected`` is; ``run_ids`` the stored runs the rows came from."""

    dataset: str
    session: date
    status: str
    present: int
    expected: int | None
    basis: str
    run_ids: tuple[str, ...] = field(default=())


@dataclass(frozen=True)
class Completeness:
    """Every dataset x the window's ``sessions`` (oldest first); ``last_closed`` the
    exchange's last closed session (later than the window's last: the store is stale)."""

    sessions: tuple[date, ...]
    datasets: tuple[str, ...]
    cells: tuple[Cell, ...]
    last_closed: date


class _Counts:
    """Row counts and run ids per (table, date), each partition read once, and each table's
    stored dates listed once (listing walks every partition directory of the table: the grid
    asks it for every cell)."""

    def __init__(self, ctx: Stores) -> None:
        self.ctx = ctx
        self._seen: dict[tuple[str, date], tuple[int, tuple[str, ...], tuple[str, ...]]] = {}
        self._stored: dict[str, tuple[date, ...]] = {}

    def stored(self, table: str) -> tuple[date, ...]:
        """``stored_dates`` of ``table``, listed once for this grid."""
        if table not in self._stored:
            self._stored[table] = stored_dates(self.ctx, table)
        return self._stored[table]

    def of(self, table: str, day: date) -> tuple[int, tuple[str, ...], tuple[str, ...]]:
        """-> (rows, run ids, statuses when the table has a ``status`` column)."""
        if (table, day) not in self._seen:
            frame = partition_on(self.ctx, table, day)
            if frame is None:
                self._seen[(table, day)] = (0, (), ())
            else:
                runs = tuple(sorted(map(str, frame["run_id"].unique())))
                statuses = tuple(map(str, frame["status"])) if "status" in frame else ()
                self._seen[(table, day)] = (len(frame), runs, statuses)
        return self._seen[(table, day)]


def _share_status(present: int, expected: int | None) -> str:
    if present == 0:
        return "MISSING"
    if expected and present < COMPLETE_SHARE * expected:
        return "PARTIAL"
    return "COMPLETE"


def _session_cell(counts: _Counts, d: Dataset, day: date) -> Cell:
    stored = counts.stored(d.name)
    earlier = [s for s in stored if s < day]
    expected = counts.of(d.name, earlier[-1])[0] if earlier else None
    basis = f"rows on {earlier[-1]}" if earlier else "no earlier session"
    present, runs, _ = counts.of(d.name, day) if day in stored else (0, (), ())
    return Cell(d.name, day, _share_status(present, expected), present, expected, basis, runs)


def _chains_cell(counts: _Counts, d: Dataset, day: date) -> Cell:
    rows, runs, statuses = counts.of(CHAIN_STATUS, day)
    try:
        optionable = load_universe(counts.ctx.reader, day).frame["optionable"]
        expected: int | None = int(optionable.fillna(False).astype(bool).sum())
    except MissingDataError:  # no universe snapshot: nothing to compare with
        expected = None
    present = sum(1 for s in statuses if s == "OK")
    status = _share_status(present, expected) if rows else "MISSING"
    return Cell(d.name, day, status, present, expected, "optionable universe, fetch OK", runs)


def _snapshot_cell(counts: _Counts, d: Dataset, day: date) -> Cell:
    snap = snapshot_on(counts.ctx, d.name, day)
    if snap is None or snap.pre_snapshot:
        return Cell(d.name, day, "MISSING", 0, None, "no snapshot on or before")
    present, runs, _ = counts.of(d.name, snap.snapshot_date)
    if snap.snapshot_date == day:
        return Cell(d.name, day, "COMPLETE", present, None, "snapshot built", runs)
    return Cell(d.name, day, "CARRIED", present, None, f"snapshot of {snap.snapshot_date}", runs)


def _cell(counts: _Counts, d: Dataset, day: date) -> Cell:
    builders: dict[str, Callable[[], Cell]] = {
        "session": lambda: _session_cell(counts, d, day),
        "chains": lambda: _chains_cell(counts, d, day),
        "snapshot": lambda: _snapshot_cell(counts, d, day),
    }
    return builders[d.kind]()


def load_completeness(
    ctx: ReadContext, sessions: int = 10, now: datetime | None = None
) -> Completeness:
    """Every dataset x the last ``sessions`` exchange sessions ending at ``ctx.session.date``,
    and the last session the exchange closed by ``now`` (default: the current time)."""
    days = sessions_ending(ctx.session.date, min(max(sessions, 1), MAX_SESSIONS))
    counts = _Counts(ctx)
    cells = tuple(_cell(counts, d, day) for d in DATASETS for day in days)
    closed = last_closed_session(now or datetime.now(UTC))
    return Completeness(tuple(days), tuple(d.name for d in DATASETS), cells, closed)


@dataclass(frozen=True)
class CellDetail:
    """One cell with the reasons behind it: ``groups`` the items not OK grouped by reason
    (chains: per underlying), ``runs`` the runs that wrote the partition and the job's runs
    that session."""

    cell: Cell
    job: str
    groups: tuple[FailureGroup, ...]
    runs: tuple[RunDetail, ...]


def load_cell_detail(ctx: ReadContext, dataset: str) -> CellDetail | None:
    """The completeness cell of ``dataset`` on ``ctx.session.date`` with the reasons behind
    it; ``None`` for a dataset the grid does not list."""
    d = BY_NAME.get(dataset)
    if d is None:
        return None
    day = ctx.session.date
    cell = _cell(_Counts(ctx), d, day)
    run_ids = [*cell.run_ids, *(r.run_id for r in ctx.reader.runs(d.job, day))]
    records = [r for r in (ctx.reader.run(i) for i in dict.fromkeys(run_ids)) if r is not None]
    items: dict[str, str] = {}
    if d.kind == "chains":
        frame = partition(ctx, CHAIN_STATUS)  # the session's own partition: the one rule
        if not isinstance(frame, Unknown):
            keys = frame["symbol"] if "symbol" in frame else frame["instrument_id"]
            items = dict(zip(keys.astype(str), frame["status"].astype(str), strict=True))
    else:
        for record in records:
            items.update(record.items)
    return CellDetail(cell, d.job, failure_groups(items), tuple(run_detail(r) for r in records))
