"""The serve-release workflow (ADR 0077 decision 4): build, promote, prune under the ``serve`` lock;
a failure is invisible (CURRENT stays), and is recorded."""

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from algotrade.data import StoreReader
from algotrade.services.jobs import exclusive_run
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.backends.release.memory import MemoryReleaseStore
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.workflows.serve_release.serve_release import (
    JOB,
    SERVE_LOCK,
    ServeStatus,
    serve_release,
)
from tests.helpers.rollup_store import write_rows
from tests.helpers.stored_frames import stamped

S1, S2 = date(2026, 10, 1), date(2026, 10, 2)
NOW = datetime(2026, 10, 3, 6, tzinfo=UTC)


def add_session(backend: MemoryBackend, writer: StoreWriter, day: date) -> None:
    bar = {"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}
    write_rows(
        writer,
        "bars/1d",
        day,
        [{"instrument_id": "EQ:AAA", "ts": pd.Timestamp(day, tz="UTC"), **bar}],
    )
    started = datetime(day.year, day.month, day.day, 22, tzinfo=UTC)
    backend.runs.save(
        RunRecord(f"nightly-{day}", "nightly", day, started, RunStatus.COMPLETE, started)
    )


@pytest.fixture
def world() -> tuple[MemoryBackend, StoreWriter, MemoryReleaseStore]:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    add_session(backend, writer, S1)
    return backend, writer, MemoryReleaseStore(backend.tables)


def test_a_build_is_promoted_pruned_and_recorded(
    world: tuple[MemoryBackend, StoreWriter, MemoryReleaseStore],
) -> None:
    backend, _, store = world
    out = serve_release(backend, store, NOW, code_sha="abc")
    assert out.status is ServeStatus.PROMOTED and out.release_id == store.releases()[0]
    current = store.current()
    assert current is not None and current[0] == out.release_id
    record = backend.runs.find(JOB)[0]
    assert record.status is RunStatus.COMPLETE and record.stats["release_id"] == out.release_id
    assert store.report().pinned_bytes is not None  # prune recorded what the pins hold


def test_a_failed_build_leaves_current_where_it_was_and_is_recorded(
    world: tuple[MemoryBackend, StoreWriter, MemoryReleaseStore],
) -> None:
    backend, writer, store = world
    first = serve_release(backend, store, NOW, code_sha="abc")
    add_session(backend, writer, S2)
    tiny = MemoryReleaseStore(backend.tables, max_bytes=1, state=store.state)  # over the ceiling
    out = serve_release(backend, tiny, NOW, code_sha="abc")
    assert out.status is ServeStatus.FAILED and "ceiling" in out.reason
    assert store.current() is not None and store.current()[0] == first.release_id  # type: ignore[index]
    failed = [r for r in backend.runs.find(JOB) if r.status is RunStatus.FAILED]
    assert len(failed) == 1 and "ceiling" in failed[0].stats["error"]
    assert store.releases() == [first.release_id]  # nothing visible, the draft was aborted


def test_nothing_is_built_while_the_current_release_serves_the_default_session(
    world: tuple[MemoryBackend, StoreWriter, MemoryReleaseStore],
) -> None:
    backend, writer, store = world
    first = serve_release(backend, store, NOW, code_sha="abc")
    frame = stamped([{"instrument_id": "EQ:AAA", "value": 1.0}], S1, "r9")
    backend.tables.write("rollups/instrument/a@v1", S1, "r9", frame, pending=True)
    backend.tables.commit_run("r9", NOW)  # a commit: the sequence moves, the session does not
    assert writer is not None
    again = serve_release(backend, store, NOW, code_sha="abc")
    assert again.status is ServeStatus.CURRENT and again.release_id == first.release_id
    rebuilt = serve_release(backend, store, NOW, code_sha="abc", rebuild=True)  # post-session: r2
    assert rebuilt.status is ServeStatus.PROMOTED and rebuilt.release_id != first.release_id
    assert store.current()[0] == rebuilt.release_id  # type: ignore[index]


def test_a_new_session_gets_a_new_release(
    world: tuple[MemoryBackend, StoreWriter, MemoryReleaseStore],
) -> None:
    backend, writer, store = world
    serve_release(backend, store, NOW, code_sha="abc")
    add_session(backend, writer, S2)
    out = serve_release(backend, store, NOW, code_sha="abc")
    assert out.status is ServeStatus.PROMOTED and out.release_id.startswith(S2.isoformat())


def test_the_serve_lock_makes_a_second_run_busy_without_touching_anything(
    world: tuple[MemoryBackend, StoreWriter, MemoryReleaseStore],
) -> None:
    backend, _, store = world
    with exclusive_run(backend, SERVE_LOCK):
        out = serve_release(backend, store, NOW, code_sha="abc")
    assert (
        out.status is ServeStatus.BUSY and store.releases() == [] and backend.runs.find(JOB) == []
    )


def test_an_empty_store_fails_quietly(
    world: tuple[MemoryBackend, StoreWriter, MemoryReleaseStore],
) -> None:
    _, _, store = world
    empty = MemoryBackend()
    out = serve_release(empty, MemoryReleaseStore(empty.tables), NOW, code_sha="abc")
    assert out.status is ServeStatus.FAILED and "nothing stored" in out.reason
    assert StoreReader(empty).dates("bars/1d") == [] and store.releases() == []
