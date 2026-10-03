"""Writer limited to job results and run records. Services may use it (ADR 0005)."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime

import pandas as pd

from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.interfaces import Backend, RunStore
from algotrade.storage.tables.schemas import result_table, validate_frame


class ResultWriter:
    def __init__(self, backend: Backend) -> None:
        self._backend = backend

    def write_result(
        self,
        name: str,
        session_date: date,
        run_id: str,
        frame: pd.DataFrame,
        pending: bool = False,
    ) -> None:
        """``pending``: visible only once ``commit_run`` (or ``publishing``) commits the run."""
        table = result_table(name)
        if "/" in name:
            raise ConfigurationError(f"result name must not contain '/': {name!r}")
        validate_frame(table, frame)
        self._backend.tables.write(table, session_date, run_id, frame, pending=pending)

    def commit_run(self, run_id: str, at: datetime) -> int:
        """Make every pending write of ``run_id`` visible at once (ADR 0022)."""
        return self._backend.tables.commit_run(run_id, at)

    def abort_run(self, run_id: str) -> int:
        """Drop every pending write of ``run_id``."""
        return self._backend.tables.abort_run(run_id)

    @contextmanager
    def publishing(self, run_id: str, at: datetime) -> Iterator[None]:
        """Write a run's results pending inside the block; commit them together when it
        ends, drop them if it raises. A crash leaves them invisible (retention drops them)."""
        try:
            yield
        except BaseException:
            self.abort_run(run_id)
            raise
        self.commit_run(run_id, at)

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
