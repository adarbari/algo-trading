"""Write facade for market and feature data. Only apps/ingestion may import this (ADR 0005)."""

from collections.abc import Sequence
from datetime import date, datetime

import pandas as pd

from algotrade.storage.tables.interfaces import Backend
from algotrade.storage.tables.result_writer import ResultWriter
from algotrade.storage.tables.schemas import validate_frame


class StoreWriter(ResultWriter):
    """Validates every frame against ``schemas.py`` before it reaches the backend."""

    def __init__(self, backend: Backend) -> None:
        super().__init__(backend)
        self.raw = backend.raw
        self.staging = backend.staging

    def write_table(
        self,
        table: str,
        session_date: date,
        run_id: str,
        frame: pd.DataFrame,
        restates: bool = False,
        pending: bool = False,
    ) -> None:
        """``restates``: ``frame`` is the partition's whole content (as read now), so earlier
        runs stop counting for merge tables (``TableStore``); a no-op for snapshot tables.
        ``pending``: visible only once the run commits (``commit_run``, ADR 0022)."""
        validate_frame(table, frame)
        self._backend.tables.write(
            table, session_date, run_id, frame, restates=restates, pending=pending
        )

    def recover_runs(self) -> list[str]:
        """Complete commits a crash interrupted (``TableStore.recover_runs``)."""
        return self._backend.tables.recover_runs()

    def pending_runs(self) -> list[str]:
        return self._backend.tables.pending_runs()

    def purge_pending_before(self, cutoff: datetime) -> int:
        """Abort runs left uncommitted, last written before ``cutoff`` (retention)."""
        return self._backend.tables.purge_pending_before(cutoff)

    def table_size(self, table: str) -> int:
        """Bytes ``table`` takes in the store (every run)."""
        return self._backend.tables.size(table)

    def build_history(self, table: str, years: Sequence[int]) -> list[int]:
        """Make the table's derived history copy hold ``years`` and be current (ADR 0060);
        -> the years built. Ingestion only (``history-copy``)."""
        return self._backend.tables.build_history(table, years)

    def history_size(self, table: str) -> int:
        """Bytes the table's history copy takes."""
        return self._backend.tables.history_size(table)

    def free_bytes(self) -> int:
        """Bytes free on the store's volume."""
        return self._backend.tables.free_bytes()

    def purge_table_before(self, table: str, cutoff: date) -> int:
        """Delete ``table``'s partitions dated before ``cutoff`` (retention: ``purge-raw``)."""
        return self._backend.tables.purge_before(table, cutoff)

    def drop_table(self, table: str) -> int:
        """Delete every partition of a superseded table (``retire-features`` only)."""
        return self._backend.tables.drop(table)
