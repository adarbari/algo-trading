"""Writer limited to ``usage/*`` tables: what the API's text model spent (ADR 0057).

The API's fifth write (ADR 0005, amended by ADR 0028 for ``live/*`` and ADR 0057):
it records every text-model attempt, and only through this writer, which refuses every table
outside ``usage/``. Each write belongs to a run and is published atomically: pending until the
run commits its partitions together, dropped if it fails (``publishing``, ADR 0022).
"""

from contextlib import AbstractContextManager
from datetime import date, datetime

import pandas as pd

from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.tables.interfaces import Backend
from algotrade.storage.tables.result_writer import ResultWriter
from algotrade.storage.tables.schemas import validate_frame

USAGE_PREFIX = "usage/"


class UsageWriter:
    def __init__(self, backend: Backend) -> None:
        self._backend = backend
        self._runs = ResultWriter(backend)  # its atomic publish, nothing else

    def write_usage(self, table: str, session_date: date, run_id: str, frame: pd.DataFrame) -> None:
        """A pending write of ``frame`` (visible once the run commits)."""
        if not table.startswith(USAGE_PREFIX):
            raise ConfigurationError(
                f"the usage writer only writes {USAGE_PREFIX}* tables: {table!r}"
            )
        validate_frame(table, frame)
        self._backend.tables.write(table, session_date, run_id, frame, pending=True)

    def publishing(self, run_id: str, at: datetime) -> AbstractContextManager[None]:
        """Writes inside the block are committed together when it ends, dropped if it raises."""
        return self._runs.publishing(run_id, at)
