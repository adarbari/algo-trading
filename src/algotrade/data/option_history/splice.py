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
Importable only by the cross-section harness and by the task that computes the groups
(``tasks/options_history``), which reads what it writes: an import-linter contract.
"""

from collections.abc import Collection, Sequence
from datetime import date, datetime, timedelta
from typing import NoReturn

import pandas as pd

from algotrade.core.model.fields import rollup_table
from algotrade.data.chains import FIRST_CBOE_CHAIN_SESSION
from algotrade.storage.tables.interfaces import Backend
from algotrade.storage.tables.readers import RecordingReader, RollingRead, StoreReader

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

    def recording(self) -> RecordingReader:
        raise NotImplementedError("the splice does not record reads for leg reuse yet; see reads")

    def _unspliced(self, what: str) -> NoReturn:
        raise NotImplementedError(
            f"SplicedReader.{what} would read the main store only: it is not spliced yet"
        )

    def with_runs_frozen(self, jobs: Collection[str]) -> StoreReader:
        self._unspliced("with_runs_frozen")

    def table_range_rolling(self, memo: RollingRead, start: date, end: date) -> pd.DataFrame | None:
        self._unspliced("table_range_rolling")

    def serves(self, table: str, day: date) -> bool:
        """Whether the history root answers a read of ``table`` on ``day``."""
        return table in CHAIN_GROUP_TABLES and day < FIRST_CBOE_CHAIN_SESSION

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
        if table not in CHAIN_GROUP_TABLES or start >= FIRST_CBOE_CHAIN_SESSION:
            return super().table_range(table, start, end, as_of, instruments, columns)
        before = min(end, FIRST_CBOE_CHAIN_SESSION - timedelta(days=1))
        parts = [self._history.table_range(table, start, before, as_of, instruments, columns)]
        for day in self._history.dates_in(table, start, before):
            self.reads.append((table, day))
        if end >= FIRST_CBOE_CHAIN_SESSION:
            parts.append(
                super().table_range(
                    table, FIRST_CBOE_CHAIN_SESSION, end, as_of, instruments, columns
                )
            )
        found = [p for p in parts if p is not None and not p.empty]
        return pd.concat(found, ignore_index=True) if found else None

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
