"""Storage protocols. Every backend implements all of them and passes tests/contract/storage."""

from collections.abc import Sequence
from datetime import date, datetime
from typing import Protocol

import pandas as pd

from algotrade.storage.runs import RunRecord


class TableStore(Protocol):
    """Point-in-time tables partitioned by (table, session_date, run_id).

    Writing the same (table, date, run) again replaces it (idempotent). A different run for
    the same date is kept alongside; readers get the latest run known at ``as_of``.
    """

    def write(self, table: str, session_date: date, run_id: str, frame: pd.DataFrame) -> None: ...

    def read(
        self,
        table: str,
        session_date: date,
        as_of: datetime | None = None,
        instruments: Sequence[str] | None = None,
    ) -> pd.DataFrame | None: ...

    def read_range(
        self,
        table: str,
        start: date,
        end: date,
        as_of: datetime | None = None,
        instruments: Sequence[str] | None = None,
    ) -> pd.DataFrame | None:
        """All partitions with ``start <= session_date <= end``, each resolved point-in-time
        exactly as ``read`` would, concatenated in date order. ``None`` if none exist."""
        ...

    def dates(self, table: str) -> list[date]: ...

    def names(self) -> list[str]:
        """Every table with at least one partition, sorted."""
        ...


class RawStore(Protocol):
    """Vendor responses exactly as received (ADR 0006), kept for a retention window."""

    def put(
        self, source: str, dataset: str, session_date: date, run_id: str, key: str, payload: bytes
    ) -> None: ...

    def get(
        self, source: str, dataset: str, session_date: date, run_id: str, key: str
    ) -> bytes | None: ...

    def purge_before(self, cutoff: date) -> int: ...


class StagingStore(Protocol):
    """Per-item scratch space for resumable jobs; published to a TableStore at the end."""

    def put(self, run_id: str, table: str, key: str, frame: pd.DataFrame) -> None: ...

    def keys(self, run_id: str, table: str) -> list[str]: ...

    def collect(self, run_id: str, table: str) -> pd.DataFrame | None: ...

    def clear(self, run_id: str) -> None: ...


class RunStore(Protocol):
    def save(self, record: RunRecord) -> None: ...

    def load(self, run_id: str) -> RunRecord | None: ...

    def find(self, job: str, session_date: date | None = None) -> list[RunRecord]: ...


class Backend(Protocol):
    @property
    def tables(self) -> TableStore: ...

    @property
    def raw(self) -> RawStore: ...

    @property
    def staging(self) -> StagingStore: ...

    @property
    def runs(self) -> RunStore: ...
