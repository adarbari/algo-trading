"""Writer limited to ``live/*`` tables: what the API read live from a market-data gateway.

The API's one write exception (ADR 0028, amending ADR 0005 and 0024): it records the live
quotes it served, and only through this writer, which refuses every table outside ``live/``.
Market and feature data stay the ingestion app's (``writers.py``). Each write belongs to a
run and is published atomically: pending until the run commits its partitions together,
dropped if it fails (``publishing``: ``ResultWriter.publishing``, ADR 0022).
"""

from contextlib import AbstractContextManager
from datetime import date, datetime

import pandas as pd

from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.tables.interfaces import Backend
from algotrade.storage.tables.result_writer import ResultWriter
from algotrade.storage.tables.schemas import validate_frame

LIVE_PREFIX = "live/"


class LiveWriter:
    def __init__(self, backend: Backend) -> None:
        self._backend = backend
        self._runs = ResultWriter(backend)  # its atomic publish, nothing else

    def write_live(self, table: str, session_date: date, run_id: str, frame: pd.DataFrame) -> None:
        """A pending write of ``frame`` (visible once the run commits)."""
        if not table.startswith(LIVE_PREFIX):
            raise ConfigurationError(
                f"the live writer only writes {LIVE_PREFIX}* tables: {table!r}"
            )
        validate_frame(table, frame)
        self._backend.tables.write(table, session_date, run_id, frame, pending=True)

    def publishing(self, run_id: str, at: datetime) -> AbstractContextManager[None]:
        """Writes inside the block are committed together when it ends, dropped if it raises."""
        return self._runs.publishing(run_id, at)
