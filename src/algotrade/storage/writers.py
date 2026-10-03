"""Write facade for market and feature data. Only apps/ingestion may import this (ADR 0005)."""

from datetime import date

import pandas as pd

from algotrade.storage.interfaces import Backend
from algotrade.storage.result_writer import ResultWriter
from algotrade.storage.schemas import validate_frame


class StoreWriter(ResultWriter):
    """Validates every frame against ``schemas.py`` before it reaches the backend."""

    def __init__(self, backend: Backend) -> None:
        super().__init__(backend)
        self.raw = backend.raw
        self.staging = backend.staging

    def write_table(self, table: str, session_date: date, run_id: str, frame: pd.DataFrame) -> None:
        validate_frame(table, frame)
        self._backend.tables.write(table, session_date, run_id, frame)
