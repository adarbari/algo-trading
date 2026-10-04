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

Also the live verification vs IBKR (``verification/ibkr``): counts by status and check, and
the failing rows.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd

from algotrade.core.model.errors import MissingDataError
from algotrade.core.time.calendar import last_closed_session, sessions_ending
from algotrade.data.chains import CHAIN_STATUS, OPTION_QUOTES
from algotrade.data.reference import UNIVERSE_TABLE, load_universe, snapshot
from algotrade.features.registry import GROUPS
from algotrade.services.explore.runs import FailureGroup, RunDetail, failure_groups, run_detail
from algotrade.services.explore.store import (
    NotFoundError,
    ReadStore,
    latest_session,
    partition_for,
    records,
)

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
    last_closed: date  # the exchange's last closed session: later than sessions[-1] = stale


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


def completeness(store: ReadStore, sessions: int = 10, now: datetime | None = None) -> Completeness:
    """Every dataset x the last ``sessions`` exchange sessions up to the latest stored one,
    and the last session the exchange closed by ``now`` (default: the current time)."""
    latest = latest_session(store.reader)
    if latest is None:
        raise NotFoundError("nothing stored")
    days = sessions_ending(latest, min(max(sessions, 1), MAX_SESSIONS))
    counts = _Counts(store)
    cells = [_cell(counts, store, d, day) for d in DATASETS for day in days]
    closed = last_closed_session(now or datetime.now(UTC))
    return Completeness(days, [d.name for d in DATASETS], cells, closed)


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


VERIFICATION = "verification/ibkr"  # our values vs IBKR's (``verify``), one row per check
VERIFY_STATUSES = ("PASS", "WARN", "FAIL", "NA")
MAX_FAILING = 50


@dataclass(frozen=True)
class CheckCounts:
    check: str  # close, hv20, iv30, option_mid, ...
    counts: dict[str, int]  # PASS / WARN / FAIL / NA -> rows


@dataclass(frozen=True)
class Verification:
    session: date  # the partition shown (latest on or before the date asked for)
    run_ids: list[str]
    instruments: int
    counts: dict[str, int]  # PASS / WARN / FAIL / NA over every row
    by_check: list[CheckCounts]  # most failures first
    failing: list[dict[str, Any]]  # FAIL then WARN rows (at most MAX_FAILING), largest diff first


def verification(store: ReadStore, on: date | None = None) -> Verification:
    """The live verification vs IBKR for the latest session on or before ``on``: counts by
    status, per check, and the failing rows; ``NotFoundError`` before the first run."""
    day = partition_for(store.reader, VERIFICATION, on)
    frame = store.reader.table(VERIFICATION, day)
    if frame is None:  # partition_for found it: only a race with a purge gets here
        raise NotFoundError(f"{VERIFICATION}: nothing stored on {day}")

    def counts(statuses: "pd.Series[str]") -> dict[str, int]:
        found = statuses.astype(str).value_counts()
        return {s: int(found.get(s, 0)) for s in VERIFY_STATUSES}

    by_check = [CheckCounts(str(c), counts(rows["status"])) for c, rows in frame.groupby("check")]
    by_check.sort(key=lambda c: (-c.counts["FAIL"], -c.counts["WARN"], c.check))
    rank = {"FAIL": 0, "WARN": 1}
    bad = frame[frame["status"].isin(list(rank))].assign(
        _rank=lambda f: f["status"].map(rank), _size=lambda f: f["diff"].abs()
    )
    bad = bad.sort_values(["_rank", "_size", "symbol"], ascending=[True, False, True])
    failing = records(bad.drop(columns=["_rank", "_size"]).head(MAX_FAILING))
    return Verification(
        session=day,
        run_ids=sorted(map(str, frame["run_id"].unique())),
        instruments=int(frame["instrument_id"].nunique()),
        counts=counts(frame["status"]),
        by_check=by_check,
        failing=failing,
    )
