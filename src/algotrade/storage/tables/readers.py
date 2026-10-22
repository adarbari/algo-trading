"""Generic read-only storage facade: tables, date ranges, partition dates and run records.

No domain rules live here (ADR 0019 R2): which snapshot to read, instruments, universes,
bars, adjustments, events and chains are ``algotrade.data``. Consumers get this class from
``algotrade.data`` and pass it to the functions there.
"""

import hashlib
from collections.abc import Collection, Hashable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import pandas as pd

from algotrade.core.model.errors import MissingDataError
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.interfaces import Backend

DATES_IN_PROBE_MAX = 366  # a longer ``dates_in`` span lists the table once instead of probing


@dataclass
class RollingRead:
    """What ``StoreReader.table_range_rolling`` keeps of its last read of one table with one column
    list: the frame, its window and each partition's commit stamp. One window at a time, the memory
    of one read."""

    table: str
    columns: tuple[str, ...]
    frame: pd.DataFrame | None = None
    start: date | None = None
    end: date | None = None
    pin: int | None = None
    epoch: int | None = None
    stamps: dict[date, int] = field(default_factory=dict)


class StoreReader:
    """``own_run``: also see that run's pending writes (the run reading what it wrote before
    it commits, ADR 0022); ``None`` (the default) sees committed data only. ``pin``: every read
    is made as of that commit sequence (``pinned``; ``TableStore.pin`` keeps its versions)."""

    def __init__(
        self, backend: Backend, own_run: str | None = None, pin: int | None = None
    ) -> None:
        self._backend = backend
        self.own_run = own_run
        self._pin = pin

    def including(self, run_id: str) -> "StoreReader":
        """This reader, also seeing ``run_id``'s pending writes."""
        return StoreReader(self._backend, run_id, self._pin)

    def recording(self) -> "RecordingReader":
        """A reader of the same store and view that logs the reads of an attributed day."""
        return RecordingReader(self._backend, self.own_run, pin=self._pin)

    @property
    def pin(self) -> int | None:
        """The commit sequence every read is made at (``pinned``), ``None`` for a live reader."""
        return self._pin

    def pinned(self, seq: int) -> "StoreReader":
        """A reader of the same store whose every read is made as of commit sequence ``seq``:
        partitions and dates committed after it are invisible, a version the store no longer
        keeps raises ``StaleSnapshotError`` (the caller falls back to a live reader). It does
        not pin the store: ``TableStore.pin`` retains the versions."""
        return StoreReader(self._backend, self.own_run, seq)

    def with_runs_frozen(self, jobs: Collection[str]) -> "StoreReader":
        """A reader whose ``runs(job, ...)`` of each of ``jobs`` answers from the records saved
        right now (the pin, if any, and ``own_run`` kept). Run records are not versioned by the
        commit sequence; a build that takes its sequence X after this call sees only records
        saved before X, which a workflow saves after the commits they name."""
        frozen = {job: tuple(self.runs(job)) for job in jobs}
        return _FrozenRuns(self._backend, self.own_run, self._pin, frozen)

    def version(self) -> Hashable:
        """What a cache over this reader's rows is keyed by: ``("pin", seq)`` for a pinned
        reader (stable while the store moves on), else ``("live", visible_seq())`` (changes
        exactly when a commit publishes)."""
        if self._pin is not None:
            return ("pin", self._pin)
        return ("live", self.visible_seq())

    def table(
        self,
        table: str,
        session_date: date,
        as_of: datetime | None = None,
        instruments: Sequence[str] | None = None,
    ) -> pd.DataFrame | None:
        tables = self._backend.tables
        return tables.read(table, session_date, as_of, instruments, self.own_run, self._pin)

    def require(
        self, table: str, session_date: date, hint: str, as_of: datetime | None = None
    ) -> pd.DataFrame:
        """Like ``table`` but raises ``MissingDataError`` instead of returning ``None``."""
        frame = self.table(table, session_date, as_of)
        if frame is None:
            raise MissingDataError(table, f"no data for {session_date.isoformat()}", hint)
        return frame

    def table_range(
        self,
        table: str,
        start: date,
        end: date,
        as_of: datetime | None = None,
        instruments: Sequence[str] | None = None,
        columns: Sequence[str] | None = None,
    ) -> pd.DataFrame | None:
        """``columns``: only these (+ ``instrument_id`` and the point-in-time columns)."""
        tables = self._backend.tables
        return tables.read_range(
            table, start, end, as_of, instruments, self.own_run, columns, self._pin
        )

    def table_range_rolling(self, memo: RollingRead, start: date, end: date) -> pd.DataFrame | None:
        """``table_range(memo.table, start, end, columns=memo.columns)``, identical rows and order,
        re-reading only the partitions after the previous call's window when the window moved on
        and every partition it still covers has the commit stamp it had (``partition_seq``): then
        the kept rows before ``start`` are dropped and the new partitions appended. Any other
        change (an earlier start, a restated, purged or inserted partition, another pin, pending
        writes of ``own_run``) re-reads the whole range. The frame is shared with ``memo``: the
        caller must not change it. The kept rows and the appended partitions come from two reads:
        harmless, since any stamp change re-reads everything."""
        epoch = self._backend.tables.destructive_epoch()  # before the stamps and the reads
        stamps = self.partition_seq(memo.table, start, end)
        kept = memo.frame
        last = memo.end
        reusable = (
            kept is not None
            and last is not None
            and memo.start is not None
            and memo.start <= start
            and last <= end
            and memo.pin == self._pin
            and memo.epoch == epoch  # a purge or direct write moves no stamp
            and self.own_run is None
            and all(stamps.get(d) == v for d, v in memo.stamps.items() if d >= start)
            and not any(d <= last and d not in memo.stamps for d in stamps)
        )
        if not reusable or kept is None or last is None:
            frame = StoreReader.table_range(self, memo.table, start, end, None, None, memo.columns)
        else:
            if memo.start != start:
                kept = kept[pd.to_datetime(kept["session_date"]) >= pd.Timestamp(start)]
            fresh = [d for d in stamps if d > last]
            added = (
                StoreReader.table_range(self, memo.table, min(fresh), end, None, None, memo.columns)
                if fresh
                else None
            )
            frame = kept if added is None else pd.concat([kept, added], ignore_index=True)
            frame = frame.reset_index(drop=True)
        memo.frame, memo.start, memo.end = frame, start, end
        memo.pin, memo.epoch, memo.stamps = self._pin, epoch, stamps
        return frame

    def read_run(
        self,
        table: str,
        session_date: date,
        run_id: str,
        columns: Sequence[str] | None = None,
        instruments: Sequence[str] | None = None,
    ) -> pd.DataFrame | None:
        """One committed run's own rows of a partition (``TableStore.read_run``)."""
        tables = self._backend.tables
        return tables.read_run(
            table, session_date, run_id, self.own_run, columns, instruments, self._pin
        )

    def read_latest_runs(
        self,
        table: str,
        session_date: date,
        group: Sequence[str] = ("user_id", "config_id"),
        columns: Sequence[str] | None = None,
        instruments: Sequence[str] | None = None,
    ) -> pd.DataFrame | None:
        """Each group's newest run of a partition (``TableStore.read_latest_runs``)."""
        tables = self._backend.tables
        return tables.read_latest_runs(
            table, session_date, group, columns, instruments, self.own_run, self._pin
        )

    def visible_seq(self) -> int:
        """The latest committed publish sequence: changes exactly when a commit publishes."""
        return self._backend.tables.visible_seq()

    def destructive_epoch(self) -> int:
        """Operations that deleted committed rows so far (``TableStore.destructive_epoch``)."""
        return self._backend.tables.destructive_epoch()

    def partition_seq(self, table: str, start: date, end: date) -> dict[date, int]:
        """Per committed partition in the range, its highest commit sequence (ADR 0063)."""
        return self._backend.tables.partition_seq(table, start, end, self._pin)

    def runs_generation(self) -> tuple[int, int]:
        """Changes exactly when a run record (a job's too) is saved: the key of a cache over the
        run records, read before them like ``visible_seq`` (ADR 0022)."""
        return self._backend.runs.generation()

    def history_current(self, table: str, day: date) -> bool:
        """Whether the table's history copy (ADR 0060) holds ``day`` as it is now: how an
        operator learns the nightly's ``history-copy`` step is behind (``make doctor``)."""
        return self._backend.tables.history_current(table, day)

    def warm_history(self, table: str) -> int:
        """Validate the table's history copy for every year (ADR 0060), at this reader's
        version: the API's warmer calls it so the first read pays no digest."""
        return self._backend.tables.warm_history(table, self._pin)

    def table_names(self) -> list[str]:
        return self._backend.tables.names(self.own_run)

    def dates(self, table: str) -> list[date]:
        return self._backend.tables.dates(table, self.own_run, self._pin)

    def has_partition(self, table: str, day: date) -> bool:
        """Whether ``dates(table)`` lists ``day``: one probe, not a listing of the table."""
        return self._backend.tables.has_partition(table, day, self.own_run, self._pin)

    def dates_in(self, table: str, start: date, end: date) -> list[date]:
        """``dates(table)`` restricted to ``start..end``, oldest first, from one index probe per
        day (live, pinned and own-run views alike): bounded by the span, not by the table's
        partitions (listing 4,000 directories to place ten sessions). A span over
        ``DATES_IN_PROBE_MAX`` days lists the table once instead, as probing would cost more."""
        span = (end - start).days + 1
        if span > DATES_IN_PROBE_MAX:
            return [d for d in self.dates(table) if start <= d <= end]
        days = (start + timedelta(days=k) for k in range(max(span, 0)))
        tables = self._backend.tables
        return [d for d in days if tables.has_partition(table, d, self.own_run, self._pin)]

    def latest_date(self, table: str, on_or_before: date | None = None) -> date | None:
        """The last partition date (on or before a date). Picking the snapshot a reader
        should see is ``algotrade.data.reference.snapshot``, not this."""
        dates = [d for d in self.dates(table) if on_or_before is None or d <= on_or_before]
        return dates[-1] if dates else None

    def earliest_date(self, table: str) -> date | None:
        """The first partition date (the stand-in of a read before every snapshot)."""
        dates = self.dates(table)
        return dates[0] if dates else None

    def runs(self, job: str, session_date: date | None = None) -> list[RunRecord]:
        return self._backend.runs.find(job, session_date)

    def runs_of(self, jobs: Collection[str], first: date, last: date) -> list[RunRecord]:
        """The records of any of ``jobs`` for the sessions ``first..last`` in one pass."""
        return self._backend.runs.find_many(jobs, first, last)

    def run(self, run_id: str) -> RunRecord | None:
        """One run record by id (``None`` when there is none)."""
        return self._backend.runs.load(run_id)


class _FrozenRuns(StoreReader):
    """A ``StoreReader`` whose run records of some jobs are a snapshot (``with_runs_frozen``)."""

    def __init__(
        self,
        backend: Backend,
        own_run: str | None,
        pin: int | None,
        frozen: dict[str, tuple[RunRecord, ...]],
    ) -> None:
        super().__init__(backend, own_run, pin)
        self._frozen = frozen

    def runs(self, job: str, session_date: date | None = None) -> list[RunRecord]:
        if job not in self._frozen:
            return super().runs(job, session_date)
        return [r for r in self._frozen[job] if session_date in (None, r.session_date)]

    def pinned(self, seq: int) -> "StoreReader":
        return _FrozenRuns(self._backend, self.own_run, seq, self._frozen)

    def including(self, run_id: str) -> "StoreReader":
        return _FrozenRuns(self._backend, run_id, self._pin, self._frozen)


@dataclass(frozen=True)
class ReadRecord:
    """One read an attributed day made. ``kind`` ``rows``: partitions ``start..end`` of
    ``table`` were read (found or not: a read that found nothing is recorded too; ``digest``, when
    the read could tell, the hash of the partition dates it returned, so a partition purged since
    is noticed); ``dates``:
    the partition dates of ``table`` the caller used were listed, ``digest`` their hash
    (``dates_digest``), ``start`` the earliest of them; ``end`` is the day, or the latest date
    listed when that is after it (a read of the future: never reusable)."""

    table: str
    start: date
    end: date
    kind: str
    digest: str | None = None


def dates_digest(days: Sequence[date]) -> str:
    """The hash of a list of partition dates: what a ``dates`` read is compared by."""
    return hashlib.sha256(",".join(d.isoformat() for d in days).encode()).hexdigest()[:16]


@dataclass
class _Attribution:
    """What the readers of one family (a ``RecordingReader`` and its ``including`` copies)
    share: the day being attributed, each day's reads and the sequence at its first read."""

    day: date | None = None
    reads: dict[date, dict[ReadRecord, None]] = field(default_factory=dict)  # ordered, deduped
    seq: dict[date, int] = field(default_factory=dict)


@dataclass
class CapturedReads:
    """The reads a block made for one day (``RecordingReader.capture``) and ``seq``, the commit
    sequence when it started."""

    seq: int
    records: tuple[ReadRecord, ...] = ()


class RecordingReader(StoreReader):
    """A ``StoreReader`` that logs, per attributed day, which partitions it read (ADR 0063).

    Inside ``attribute(day)`` every ``table`` / ``require`` / ``table_range`` / ``dates`` /
    ``latest_date`` read is logged against ``day``, including one that found nothing, and the
    first read of a day also stamps ``inputs_seq(day)`` with ``visible_seq()`` taken before the
    read. A reader whose day's logged reads still match (``partition_seq`` per ``rows`` read,
    ``dates_digest`` per ``dates`` read) can reuse what that day computed. Reads outside any
    ``attribute`` block belong to the run, not to a day, and are not logged. One attributed
    day at a time: attribution is not thread-safe."""

    def __init__(
        self,
        backend: Backend,
        own_run: str | None = None,
        _shared: _Attribution | None = None,
        pin: int | None = None,
    ) -> None:
        super().__init__(backend, own_run, pin)
        self._attr = _shared if _shared is not None else _Attribution()

    def including(self, run_id: str) -> "RecordingReader":
        return RecordingReader(self._backend, run_id, self._attr, self._pin)

    def pinned(self, seq: int) -> "RecordingReader":
        """As ``StoreReader.pinned``, logging into the same attribution."""
        return RecordingReader(self._backend, self.own_run, self._attr, seq)

    @contextmanager
    def attribute(self, day: date) -> Iterator[None]:
        """Log the reads made inside the block against ``day`` (blocks do not nest)."""
        if self._attr.day is not None:
            raise RuntimeError(f"already attributing {self._attr.day}: attribute() does not nest")
        self._attr.day = day
        try:
            yield
        finally:
            self._attr.day = None

    def reads(self, day: date) -> tuple[ReadRecord, ...]:
        """The reads attributed to ``day``, first to last, each distinct read once."""
        return tuple(self._attr.reads.get(day, {}))

    def inputs_seq(self, day: date) -> int | None:
        """``visible_seq()`` at ``day``'s first read; ``None`` when it read nothing."""
        return self._attr.seq.get(day)

    def attributed_days(self) -> list[date]:
        return sorted(self._attr.reads)

    @contextmanager
    def capture(self, day: date) -> Iterator["CapturedReads"]:
        """Run the block's reads of the attributed ``day`` into a log of their own and merge it
        into the day's afterwards: ``CapturedReads`` holds what the block read and the sequence
        it started at, so a computation can be handed to another reader (``replay``). A block
        that reads nothing leaves the day as it was (no sequence is stamped for it)."""
        attr = self._attr
        if attr.day != day:
            raise RuntimeError(f"capture({day}) outside attribute({day}): attributing {attr.day}")
        out = CapturedReads(self.visible_seq())
        outer = attr.reads.get(day)
        attr.reads[day] = {}
        try:
            yield out
        finally:
            mine = attr.reads[day]
            out.records = tuple(mine)
            if outer is None and not mine:
                del attr.reads[day]
            else:
                attr.reads[day] = {**(outer or {}), **mine}
                if outer is None:
                    attr.seq[day] = out.seq

    def replay(self, day: date, captured: "CapturedReads") -> None:
        """Log ``captured`` against ``day`` as if this reader had made those reads: the day's
        sequence becomes the earlier of its own and the capture's (a partition committed since
        the capture started is then never read as unchanged, ADR 0063)."""
        if not captured.records:
            return
        attr = self._attr
        log = attr.reads.setdefault(day, {})
        log.update(dict.fromkeys(captured.records))
        attr.seq[day] = min(attr.seq.get(day, captured.seq), captured.seq)

    def _log(self, record: ReadRecord) -> None:
        self._attr.reads[self._attr.day][record] = None  # type: ignore[index]

    def _open(self) -> bool:
        """Start logging a read: stamps the day's first, before the read it precedes."""
        day = self._attr.day
        if day is None:
            return False
        if day not in self._attr.reads:
            self._attr.reads[day] = {}
            self._attr.seq[day] = self.visible_seq()
        return True

    def table(
        self,
        table: str,
        session_date: date,
        as_of: datetime | None = None,
        instruments: Sequence[str] | None = None,
    ) -> pd.DataFrame | None:
        recording = self._open()
        frame = super().table(table, session_date, as_of, instruments)
        if recording:
            self._log_rows(table, session_date, session_date)
        return frame

    def table_range(
        self,
        table: str,
        start: date,
        end: date,
        as_of: datetime | None = None,
        instruments: Sequence[str] | None = None,
        columns: Sequence[str] | None = None,
    ) -> pd.DataFrame | None:
        recording = self._open()
        frame = super().table_range(table, start, end, as_of, instruments, columns)
        if recording:
            self._log_rows(table, start, end)
        return frame

    def table_range_rolling(self, memo: RollingRead, start: date, end: date) -> pd.DataFrame | None:
        recording = self._open()
        frame = super().table_range_rolling(memo, start, end)
        if recording:
            self._log_rows(memo.table, start, end)  # the read it stands for, every partition
        return frame

    def read_run(
        self,
        table: str,
        session_date: date,
        run_id: str,
        columns: Sequence[str] | None = None,
        instruments: Sequence[str] | None = None,
    ) -> pd.DataFrame | None:
        recording = self._open()
        frame = super().read_run(table, session_date, run_id, columns, instruments)
        if recording:
            self._log_rows(table, session_date, session_date)
        return frame

    def read_latest_runs(
        self,
        table: str,
        session_date: date,
        group: Sequence[str] = ("user_id", "config_id"),
        columns: Sequence[str] | None = None,
        instruments: Sequence[str] | None = None,
    ) -> pd.DataFrame | None:
        recording = self._open()
        frame = super().read_latest_runs(table, session_date, group, columns, instruments)
        if recording:
            self._log_rows(table, session_date, session_date)
        return frame

    def _log_rows(self, table: str, start: date, end: date) -> None:
        """Log a ``rows`` read with the committed partition dates the store lists in the range
        (not what the read returned: a filtered read cannot tell an empty partition from none)."""
        listed = sorted(StoreReader.partition_seq(self, table, start, end))
        self._log(ReadRecord(table, start, end, "rows", dates_digest(listed)))

    def _log_dates(self, table: str, seen: list[date]) -> None:
        """Log the listing the caller used. A date after the day is a read of the future: the
        record then ends there, and its digest covers it, so it never stays valid."""
        day = self._attr.day
        assert day is not None
        first, last = (seen[0], max(seen[-1], day)) if seen else (day, day)
        self._log(ReadRecord(table, first, last, "dates", dates_digest(seen)))

    def dates(self, table: str) -> list[date]:
        recording = self._open()  # before the read: the sequence it will be stamped with
        found = super().dates(table)
        if recording:
            self._log_dates(table, found)
        return found

    def has_partition(self, table: str, day: date) -> bool:
        """A membership test is a read of the listing: recorded as one (its digest)."""
        return day in self.dates(table)

    def dates_in(self, table: str, start: date, end: date) -> list[date]:
        """A windowed listing is still a read of the listing for the record (its digest)."""
        return [d for d in self.dates(table) if start <= d <= end]

    def latest_date(self, table: str, on_or_before: date | None = None) -> date | None:
        recording = self._open()
        found = StoreReader.dates(self, table)  # not self.dates: logged here, once
        seen = [d for d in found if on_or_before is None or d <= on_or_before]
        if recording:
            self._log_dates(table, seen)
        return seen[-1] if seen else None

    def earliest_date(self, table: str) -> date | None:
        """Logged as the one partition it names: a later partition never changes the answer,
        an earlier one does (``dates`` digest of ``[first]``)."""
        recording = self._open()
        found = StoreReader.dates(self, table)
        if recording and found:
            self._log(ReadRecord(table, found[0], found[0], "dates", dates_digest(found[:1])))
        return found[0] if found else None
