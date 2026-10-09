"""Storage contract, the runs generation: ``RunStore.generation()`` moves on every ``save`` of a
run record (a new one, or a changed one) and on nothing else, so a cache over the run records
(the GraphQL response cache) is exact while it is unchanged."""

from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.interfaces import Backend
from algotrade.storage.tables.readers import StoreReader

AT = datetime(2026, 10, 1, 12, tzinfo=UTC)


@pytest.fixture(params=["memory", "local"])
def backend(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Backend]:
    yield MemoryBackend() if request.param == "memory" else LocalBackend(tmp_path / "data")


def record(run_id: str = "job-2026-10-01-a") -> RunRecord:
    return RunRecord(run_id=run_id, job="job", session_date=date(2026, 10, 1), started_at=AT)


def test_a_save_moves_the_generation_each_time(backend: Backend) -> None:
    seen = [backend.runs.generation()]
    for n in range(5):
        backend.runs.save(record(f"job-2026-10-01-{n}"))
        seen.append(backend.runs.generation())
    backend.runs.save(record("job-2026-10-01-0"))  # the same run saved again (its status moved)
    seen.append(backend.runs.generation())
    assert len(set(seen)) == len(seen)


def test_a_read_does_not_move_the_generation(backend: Backend) -> None:
    backend.runs.save(record())
    before = backend.runs.generation()
    backend.runs.load("job-2026-10-01-a")
    backend.runs.find("job")
    backend.runs.find_many(["job"], date(2026, 9, 1), date(2026, 10, 9))
    StoreReader(backend).runs("job")
    assert backend.runs.generation() == before


def test_the_reader_exposes_the_generation(backend: Backend) -> None:
    reader = StoreReader(backend)
    before = reader.runs_generation()
    backend.runs.save(record())
    assert reader.runs_generation() != before


def test_a_store_without_runs_has_a_generation(tmp_path: Path) -> None:
    assert LocalBackend(tmp_path / "empty").runs.generation() == (0, 0)
