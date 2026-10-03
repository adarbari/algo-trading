"""Writer limited to job results and run records. Services may use it (ADR 0005)."""

from datetime import date

import pandas as pd

from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.interfaces import Backend, RunStore
from algotrade.storage.tables.schemas import validate_frame


class ResultWriter:
    def __init__(self, backend: Backend) -> None:
        self._backend = backend

    def write_result(self, name: str, session_date: date, run_id: str, frame: pd.DataFrame) -> None:
        table = f"results/{name}"
        if "/" in name:
            raise ConfigurationError(f"result name must not contain '/': {name!r}")
        validate_frame(table, frame)
        self._backend.tables.write(table, session_date, run_id, frame)

    def save_run(self, record: RunRecord) -> None:
        self._backend.runs.save(record)

    def load_run(self, run_id: str) -> RunRecord | None:
        return self._backend.runs.load(run_id)

    @property
    def runs_backend(self) -> RunStore:
        """The run-record store (job records live here too)."""
        return self._backend.runs

    def runs_for(self, job: str, session_date: date | None = None) -> list[RunRecord]:
        return self._backend.runs.find(job, session_date)
