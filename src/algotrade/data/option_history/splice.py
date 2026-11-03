"""The ``StoreReader`` splice of the pre-cutover chain feature groups (ADR 0088 decision 11, F7).

The chain feature groups (``iv30@v1``, ``iv_history@v2``, ``implied_move@v1``,
``option_liquidity@v1``, ``iv_term@v1``, ``skew@v1``, ``nearest_expiry@v1``, ``put_wing@v1``,
``call_wing@v1``) are computed for the sessions before ``FIRST_CBOE_CHAIN_SESSION`` from the bought
history and stored in the history root under the same names (licence personal, a feature's licence
cannot vary by row). ``SplicedReader`` is the main store's reader that sends a read of one of those
tables for a session before the cutover to the history root and any other read (every table from
the cutover on, every other table) to the main store: one source per session, never merged (H6). A
range read that spans the cutover is the history part before it and the main part from it.

Every partition read from the history root is logged (``reads``): a trial that read through the
splice is ``personal`` (``licence``), the strictest-of-what-it-read rule of ADR 0088 decision 11.
The harness's history slice reads through ``spliced``; its leg-reuse record (ADR 0063) is
``SplicedRecordingReader``: a read from the root is a ``stamped`` record (the root has its own
commit sequence, so its partitions' own stamps are kept rather than compared with the main store's
``inputs_seq``), and a stored leg whose record holds one keeps the trial personal when it is reused
(``read_licence``). Importable only by the cross-section harness and by the task that computes the
groups (``tasks/options_history``), which reads what it writes: an import-linter contract.
"""

from collections.abc import Callable, Collection, Iterable, Sequence
from datetime import date, datetime, timedelta
from typing import NoReturn

import pandas as pd

from algotrade.core.model.fields import rollup_table
from algotrade.data.chains import FIRST_CBOE_CHAIN_SESSION
from algotrade.data.option_history.store import open_history
from algotrade.storage.tables.interfaces import Backend, PartitionStats, RowFilter
from algotrade.storage.tables.readers import (
    STAMPED,
    ReadRecord,
    RecordingReader,
    RollingRead,
    StoreReader,
    _Attribution,
    stamps_digest,
)

CHAIN_GROUPS = (
    "iv30@v1",
    "iv_history@v2",
    "implied_move@v1",
    "option_liquidity@v1",
    "iv_term@v1",
    "skew@v1",
    "nearest_expiry@v1",
    "put_wing@v1",
    "call_wing@v1",
)  # fmt: skip  (a group before the groups that read its rows: iv_history after iv30)
CHAIN_GROUP_TABLES = frozenset(rollup_table("instrument", key) for key in CHAIN_GROUPS)
PERSONAL = "personal"
OPEN = "open"
LAST_HISTORY_SESSION = FIRST_CBOE_CHAIN_SESSION - timedelta(days=1)


class SplicedReader(StoreReader):
    """The main store's reader, with the chain groups' tables of sessions before the cutover read
    from ``history`` (a reader of the option-history store)."""

    def __init__(
        self,
        backend: Backend,
        history: StoreReader,
        own_run: str | None = None,
        pin: int | None = None,
        reads: list[tuple[str, date]] | None = None,
    ) -> None:
        super().__init__(backend, own_run, pin)
        self._history = history
        self.reads: list[tuple[str, date]] = [] if reads is None else reads

    @property
    def licence(self) -> str | None:
        """``personal`` once a partition came from the history root, else ``None``."""
        return PERSONAL if self.reads else None

    def _clone(self, own_run: str | None, pin: int | None) -> "SplicedReader":
        """The same splice over another view of the main store (sharing the ``reads`` log)."""
        return SplicedReader(self._backend, self._history, own_run, pin, self.reads)

    def including(self, run_id: str) -> "SplicedReader":
        return self._clone(run_id, self._pin)

    def pinned(self, seq: int) -> "SplicedReader":
        self._unspliced("pinned")  # a pin is a main-store commit sequence: the history has its own

    def recording(self) -> "SplicedRecordingReader":
        """The splice's leg-reuse recorder (``SplicedRecordingReader``), sharing ``reads``."""
        return SplicedRecordingReader(self)

    def _unspliced(self, what: str) -> NoReturn:
        raise NotImplementedError(
            f"SplicedReader.{what} would read the main store only: it is not spliced yet"
        )

    def with_runs_frozen(self, jobs: Collection[str]) -> StoreReader:
        self._unspliced("with_runs_frozen")

    def table_range_rolling(self, memo: RollingRead, start: date, end: date) -> pd.DataFrame | None:
        """A chain group's window from before the cutover is read whole (two stores, two commit
        sequences: no memo); any other is the main store's rolling read."""
        if not self.serves(memo.table, start):
            return super().table_range_rolling(memo, start, end)
        return self.table_range(memo.table, start, end, columns=memo.columns)

    def serves(self, table: str, day: date) -> bool:
        """Whether the history root answers a read of ``table`` on ``day`` (of a range from
        ``day``: its part before the cutover)."""
        return table in CHAIN_GROUP_TABLES and day < FIRST_CBOE_CHAIN_SESSION

    def _guard(self, table: str, day: date, what: str) -> None:
        """A read the splice does not route must not answer from the main store alone."""
        if self.serves(table, day):
            self._unspliced(what)

    def partition_seq(self, table: str, start: date, end: date) -> dict[date, int]:
        """Each partition's commit sequence in the store that answers it: a chain group's before
        the cutover the history root's (its own sequence, never comparable with the main store's
        ``visible_seq``: the recorder logs such a read as ``stamped``), any other the main's."""
        if not self.serves(table, start):
            return super().partition_seq(table, start, end)
        found = self._history.partition_seq(table, start, min(end, LAST_HISTORY_SESSION))
        if end >= FIRST_CBOE_CHAIN_SESSION:
            found.update(super().partition_seq(table, FIRST_CBOE_CHAIN_SESSION, end))
        return found

    def read_run(
        self,
        table: str,
        session_date: date,
        run_id: str,
        columns: Sequence[str] | None = None,
        instruments: Sequence[str] | None = None,
        where: Sequence[RowFilter] = (),
    ) -> pd.DataFrame | None:
        self._guard(table, session_date, "read_run")
        return super().read_run(table, session_date, run_id, columns, instruments, where)

    def partition_stats(
        self, table: str, session_date: date, column: str | None = None
    ) -> PartitionStats | None:
        self._guard(table, session_date, "partition_stats")
        return super().partition_stats(table, session_date, column)

    def read_latest_runs(
        self,
        table: str,
        session_date: date,
        group: Sequence[str] = ("user_id", "config_id"),
        columns: Sequence[str] | None = None,
        instruments: Sequence[str] | None = None,
    ) -> pd.DataFrame | None:
        self._guard(table, session_date, "read_latest_runs")
        return super().read_latest_runs(table, session_date, group, columns, instruments)

    def _history_table(
        self, table: str, day: date, as_of: datetime | None, instruments: Sequence[str] | None
    ) -> pd.DataFrame | None:
        frame = self._history.table(table, day, as_of, instruments)
        if frame is not None:
            self.reads.append((table, day))
        return frame

    def table(
        self,
        table: str,
        session_date: date,
        as_of: datetime | None = None,
        instruments: Sequence[str] | None = None,
    ) -> pd.DataFrame | None:
        if self.serves(table, session_date):
            return self._history_table(table, session_date, as_of, instruments)
        return super().table(table, session_date, as_of, instruments)

    def table_range(
        self,
        table: str,
        start: date,
        end: date,
        as_of: datetime | None = None,
        instruments: Sequence[str] | None = None,
        columns: Sequence[str] | None = None,
    ) -> pd.DataFrame | None:
        if not self.serves(table, start):
            return super().table_range(table, start, end, as_of, instruments, columns)
        before = min(end, LAST_HISTORY_SESSION)
        parts = [self._history.table_range(table, start, before, as_of, instruments, columns)]
        for day in self._history.dates_in(table, start, before):
            self.reads.append((table, day))
        if end >= FIRST_CBOE_CHAIN_SESSION:
            parts.append(
                super().table_range(
                    table, FIRST_CBOE_CHAIN_SESSION, end, as_of, instruments, columns
                )
            )
        return _joined(parts)

    def dates(self, table: str) -> list[date]:
        if table not in CHAIN_GROUP_TABLES:
            return super().dates(table)
        early = [d for d in self._history.dates(table) if d < FIRST_CBOE_CHAIN_SESSION]
        return early + [d for d in super().dates(table) if d >= FIRST_CBOE_CHAIN_SESSION]

    def has_partition(self, table: str, day: date) -> bool:
        if self.serves(table, day):
            return self._history.has_partition(table, day)
        return super().has_partition(table, day)

    def dates_in(self, table: str, start: date, end: date) -> list[date]:
        return [d for d in self.dates(table) if start <= d <= end]


def _joined(parts: Sequence[pd.DataFrame | None]) -> pd.DataFrame | None:
    """The history part and the main part of a range read, in that order (None: neither holds a
    row)."""
    found = [p for p in parts if p is not None and not p.empty]
    return pd.concat(found, ignore_index=True) if found else None


class SplicedRecordingReader(RecordingReader):
    """``SplicedReader.recording``: the per-day log of reads leg reuse checks (ADR 0063) over the
    splice. A read the splice sends to the history root is logged as ``stamped``, its partitions'
    commit sequences in the root taken before the read (a partition restated after them is never
    read as unchanged); a read of the main store, and the main part of a range spanning the
    cutover, as ``RecordingReader`` logs it; a chain group's listing is the splice's. Reads of the
    root also land in the splice's ``reads`` (the licence)."""

    def __init__(self, splice: SplicedReader, _shared: _Attribution | None = None) -> None:
        super().__init__(splice._backend, splice.own_run, _shared, splice.pin)
        self._splice = splice

    def including(self, run_id: str) -> "SplicedRecordingReader":
        return SplicedRecordingReader(self._splice.including(run_id), self._attr)

    def pinned(self, seq: int) -> NoReturn:
        self._splice._unspliced("pinned")

    def recording(self) -> "SplicedRecordingReader":
        return SplicedRecordingReader(self._splice)

    def with_runs_frozen(self, jobs: Collection[str]) -> StoreReader:
        self._splice._unspliced("with_runs_frozen")

    def partition_seq(self, table: str, start: date, end: date) -> dict[date, int]:
        return self._splice.partition_seq(table, start, end)

    def _listing(self, table: str) -> list[date]:
        return self._splice.dates(table)

    def _stamped(
        self, table: str, start: date, end: date, read: Callable[[], pd.DataFrame | None]
    ) -> pd.DataFrame | None:
        """``read`` (a read of the history root), logged as one ``stamped`` record."""
        recording = self._open()
        stamps = self._splice._history.partition_seq(table, start, end) if recording else {}
        frame = read()
        if recording:
            self._log(ReadRecord(table, start, end, STAMPED, stamps_digest(stamps)))
        return frame

    def table(
        self,
        table: str,
        session_date: date,
        as_of: datetime | None = None,
        instruments: Sequence[str] | None = None,
    ) -> pd.DataFrame | None:
        if not self._splice.serves(table, session_date):
            return super().table(table, session_date, as_of, instruments)
        return self._stamped(
            table,
            session_date,
            session_date,
            lambda: self._splice.table(table, session_date, as_of, instruments),
        )

    def table_range(
        self,
        table: str,
        start: date,
        end: date,
        as_of: datetime | None = None,
        instruments: Sequence[str] | None = None,
        columns: Sequence[str] | None = None,
    ) -> pd.DataFrame | None:
        if not self._splice.serves(table, start):
            return super().table_range(table, start, end, as_of, instruments, columns)
        before = min(end, LAST_HISTORY_SESSION)
        parts = [
            self._stamped(
                table,
                start,
                before,
                lambda: self._splice.table_range(table, start, before, as_of, instruments, columns),
            )
        ]
        if end >= FIRST_CBOE_CHAIN_SESSION:
            parts.append(
                super().table_range(
                    table, FIRST_CBOE_CHAIN_SESSION, end, as_of, instruments, columns
                )
            )
        return _joined(parts)

    def table_range_rolling(self, memo: RollingRead, start: date, end: date) -> pd.DataFrame | None:
        if not self._splice.serves(memo.table, start):
            return super().table_range_rolling(memo, start, end)
        return self.table_range(memo.table, start, end, columns=memo.columns)

    def read_run(
        self,
        table: str,
        session_date: date,
        run_id: str,
        columns: Sequence[str] | None = None,
        instruments: Sequence[str] | None = None,
        where: Sequence[RowFilter] = (),
    ) -> pd.DataFrame | None:
        self._splice._guard(table, session_date, "read_run")
        return super().read_run(table, session_date, run_id, columns, instruments, where)

    def partition_stats(
        self, table: str, session_date: date, column: str | None = None
    ) -> PartitionStats | None:
        self._splice._guard(table, session_date, "partition_stats")
        return super().partition_stats(table, session_date, column)

    def read_latest_runs(
        self,
        table: str,
        session_date: date,
        group: Sequence[str] = ("user_id", "config_id"),
        columns: Sequence[str] | None = None,
        instruments: Sequence[str] | None = None,
    ) -> pd.DataFrame | None:
        self._splice._guard(table, session_date, "read_latest_runs")
        return super().read_latest_runs(table, session_date, group, columns, instruments)


def history_store(url: str | None) -> StoreReader:
    """A reader of the option-history root at ``url`` (``HistoryUnavailableError`` when it is not
    set, not mounted or has no sentinel)."""
    return StoreReader(open_history(url))


def spliced(reader: StoreReader, history: StoreReader) -> SplicedReader:
    """The cross-section harness's reader of an option edge's history slice (ADR 0088 decision
    11): ``reader``'s store and view, the chain groups' tables before the cutover read from
    ``history``. A pinned ``reader`` raises: a pin is a main-store sequence the root does not
    share."""
    if reader.pin is not None:
        raise NotImplementedError("the splice of a pinned reader would leave the history unpinned")
    return SplicedReader(reader._backend, history, reader.own_run)


def read_licence(reader: StoreReader, logged: Iterable[ReadRecord]) -> str:
    """``personal`` when ``reader`` (a ``SplicedReader``) read a partition from the history root or
    any of ``logged`` (the reuse records of the legs a run kept) was such a read; else ``open``.
    A reused leg's reads were not made again, so its record is what says the trial read the root."""
    if isinstance(reader, SplicedReader) and reader.licence == PERSONAL:
        return PERSONAL
    return PERSONAL if any(r.kind == STAMPED for r in logged) else OPEN
