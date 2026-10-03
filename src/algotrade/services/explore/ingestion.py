"""Ingestion completeness for the admin pages: per dataset and session, the rows present
against the rows expected, and a drill-down into one cell (item statuses grouped by reason,
the runs that wrote it).

Expected rows, per kind of dataset:
- ``session`` (bars, rollups): the rows of the dataset's previous stored session (a drop is
  the signal, as the quality checks use it); COMPLETE at 98% or more, PARTIAL below, MISSING
  without a partition.
- ``chains``: underlyings whose chain fetch is ``OK`` (``chains/status``) against the
  optionable instruments of the universe snapshot the session sees.
- ``snapshot`` (reference, universe): COMPLETE when a snapshot was built that session,
  CARRIED when an earlier one stands in, MISSING before the first.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from algotrade.core.model.errors import MissingDataError
from algotrade.core.time.calendar import sessions_ending
from algotrade.data.chains import CHAIN_STATUS, OPTION_QUOTES
from algotrade.data.reference import UNIVERSE_TABLE, load_universe, snapshot
from algotrade.features.registry import ROLLUPS
from algotrade.services.explore.runs import FailureGroup, RunDetail, failure_groups, run_detail
from algotrade.services.explore.store import NotFoundError, ReadStore, latest_session

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
    *(Dataset(r.table, "rollups", "session") for r in ROLLUPS.values()),
)
BY_NAME = {d.name: d for d in DATASETS}


@dataclass(frozen=True)
class Cell:
    dataset: str
    session: date
    status: str  # COMPLETE | PARTIAL | MISSING | CARRIED
    present: int
    expected: int | None
    basis: str  # what ``expected`` is
    run_ids: list[str] = field(default_factory=list)  # the stored runs the rows came from


@dataclass(frozen=True)
class Completeness:
    sessions: list[date]  # oldest first
    datasets: list[str]
    cells: list[Cell]


class _Counts:
    """Row counts and run ids per (table, date), each partition read once."""

    def __init__(self, store: ReadStore) -> None:
        self.reader = store.reader
        self._seen: dict[tuple[str, date], tuple[int, list[str], list[str]]] = {}

    def of(self, table: str, day: date) -> tuple[int, list[str], list[str]]:
        """-> (rows, run ids, statuses when the table has a ``status`` column)."""
        if (table, day) not in self._seen:
            frame = self.reader.table(table, day)
            if frame is None:
                self._seen[(table, day)] = (0, [], [])
            else:
                runs = sorted(map(str, frame["run_id"].unique()))
                statuses = list(map(str, frame["status"])) if "status" in frame else []
                self._seen[(table, day)] = (len(frame), runs, statuses)
        return self._seen[(table, day)]


def _share_status(present: int, expected: int | None) -> str:
    if present == 0:
        return "MISSING"
    if expected and present < COMPLETE_SHARE * expected:
        return "PARTIAL"
    return "COMPLETE"


def _session_cell(counts: _Counts, d: Dataset, day: date, stored: list[date]) -> Cell:
    earlier = [s for s in stored if s < day]
    expected = counts.of(d.name, earlier[-1])[0] if earlier else None
    basis = f"rows on {earlier[-1]}" if earlier else "no earlier session"
    present, runs, _ = counts.of(d.name, day) if day in stored else (0, [], [])
    return Cell(d.name, day, _share_status(present, expected), present, expected, basis, runs)


def _chains_cell(counts: _Counts, store: ReadStore, d: Dataset, day: date) -> Cell:
    rows, runs, statuses = counts.of(CHAIN_STATUS, day)
    try:
        optionable = load_universe(store.reader, day).frame["optionable"]
        expected: int | None = int(optionable.fillna(False).astype(bool).sum())
    except MissingDataError:  # no universe snapshot: nothing to compare with
        expected = None
    present = sum(1 for s in statuses if s == "OK")
    status = _share_status(present, expected) if rows else "MISSING"
    return Cell(d.name, day, status, present, expected, "optionable universe, fetch OK", runs)


def _snapshot_cell(counts: _Counts, store: ReadStore, d: Dataset, day: date) -> Cell:
    snap = snapshot(store.reader, d.name, day)
    if snap is None or snap.pre_snapshot:
        return Cell(d.name, day, "MISSING", 0, None, "no snapshot on or before")
    present, runs, _ = counts.of(d.name, snap.snapshot_date)
    if snap.snapshot_date == day:
        return Cell(d.name, day, "COMPLETE", present, None, "snapshot built", runs)
    return Cell(d.name, day, "CARRIED", present, None, f"snapshot of {snap.snapshot_date}", runs)


def _cell(counts: _Counts, store: ReadStore, d: Dataset, day: date) -> Cell:
    builders: dict[str, Callable[[], Cell]] = {
        "session": lambda: _session_cell(counts, d, day, store.reader.dates(d.name)),
        "chains": lambda: _chains_cell(counts, store, d, day),
        "snapshot": lambda: _snapshot_cell(counts, store, d, day),
    }
    return builders[d.kind]()


def completeness(store: ReadStore, sessions: int = 10) -> Completeness:
    """Every dataset x the last ``sessions`` exchange sessions up to the latest stored one."""
    latest = latest_session(store.reader)
    if latest is None:
        raise NotFoundError("nothing stored")
    days = sessions_ending(latest, min(max(sessions, 1), MAX_SESSIONS))
    counts = _Counts(store)
    cells = [_cell(counts, store, d, day) for d in DATASETS for day in days]
    return Completeness(days, [d.name for d in DATASETS], cells)


@dataclass(frozen=True)
class CellDetail:
    cell: Cell
    job: str
    groups: list[FailureGroup]  # items not OK, grouped by reason (chains: per underlying)
    runs: list[RunDetail]  # the runs that wrote the partition, and the job's runs that session


def dataset_session(store: ReadStore, dataset: str, session: date) -> CellDetail:
    """One completeness cell with the reasons behind it."""
    d = BY_NAME.get(dataset)
    if d is None:
        raise NotFoundError(f"no dataset {dataset!r}; one of {sorted(BY_NAME)}")
    counts = _Counts(store)
    cell = _cell(counts, store, d, session)
    run_ids = [*cell.run_ids, *(r.run_id for r in store.reader.runs(d.job, session))]
    runs = [run_detail(store, r) for r in dict.fromkeys(run_ids) if store.reader.run(r)]
    items: dict[str, str] = {}
    if d.kind == "chains":
        frame = store.reader.table(CHAIN_STATUS, session)
        if frame is not None:
            keys = frame["symbol"] if "symbol" in frame else frame["instrument_id"]
            items = dict(zip(keys.astype(str), frame["status"].astype(str), strict=True))
    else:
        for run_id in dict.fromkeys(r.run_id for r in runs):
            record = store.reader.run(run_id)
            items.update(record.items if record else {})
    return CellDetail(cell, d.job, failure_groups(items), runs)
