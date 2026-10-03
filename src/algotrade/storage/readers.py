"""Read-only storage facade handed to backtests, screening, the API and features."""

from collections.abc import Sequence
from datetime import date, datetime

import pandas as pd

from algotrade.core.errors import MissingDataError
from algotrade.storage.interfaces import Backend
from algotrade.storage.runs import RunRecord


class StoreReader:
    def __init__(self, backend: Backend) -> None:
        self._backend = backend

    def table(
        self,
        table: str,
        session_date: date,
        as_of: datetime | None = None,
        instruments: Sequence[str] | None = None,
    ) -> pd.DataFrame | None:
        return self._backend.tables.read(table, session_date, as_of, instruments)

    def require(
        self, table: str, session_date: date, hint: str, as_of: datetime | None = None
    ) -> pd.DataFrame:
        """Like ``table`` but raises ``MissingDataError`` instead of returning ``None``."""
        frame = self.table(table, session_date, as_of)
        if frame is None:
            raise MissingDataError(table, f"no data for {session_date.isoformat()}", hint)
        return frame

    def dates(self, table: str) -> list[date]:
        return self._backend.tables.dates(table)

    def latest_date(self, table: str, on_or_before: date | None = None) -> date | None:
        dates = [d for d in self.dates(table) if on_or_before is None or d <= on_or_before]
        return dates[-1] if dates else None

    def runs(self, job: str, session_date: date | None = None) -> list[RunRecord]:
        return self._backend.runs.find(job, session_date)
