"""The release build (ADR 0077): the session record at one pinned sequence, written so that two
builds of the same store are byte for byte equal, restarted when a version it needs is lost."""

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from algotrade.data import StoreReader
from algotrade.services.read.session import resolve_session
from algotrade.services.serving.build import (
    FORMAT,
    MAX_TRIES,
    SESSION_COLUMNS,
    build_release,
    session_frame,
)
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.backends.release.memory import MemoryReleaseStore
from algotrade.storage.backends.run_selection import StaleSnapshotError
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.rollup_store import write_rows

S1, S2 = date(2026, 10, 1), date(2026, 10, 2)


def populated() -> tuple[MemoryBackend, StoreWriter]:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    for day in (S1, S2):
        bar = {"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}
        row = {"instrument_id": "EQ:AAA", "ts": pd.Timestamp(day, tz="UTC"), **bar}
        write_rows(writer, "bars/1d", day, [row])
        started = datetime(day.year, day.month, day.day, 22, tzinfo=UTC)
        record = RunRecord(f"nightly-{day}", "nightly", day, started, RunStatus.COMPLETE, started)
        backend.runs.save(record)
    return backend, writer


def build(backend: MemoryBackend, code: str = "abc") -> tuple[MemoryReleaseStore, bytes]:
    store = MemoryReleaseStore(backend.tables)
    manifest = build_release(StoreReader(backend), store, code)
    return store, manifest.to_json()


def test_two_builds_of_the_same_store_are_equal_in_manifest_and_session_bytes() -> None:
    first, _ = populated()
    second, _ = populated()
    store_a, manifest_a = build(first)
    store_b, manifest_b = build(second)
    assert manifest_a == manifest_b
    release_id = store_a.releases()[0]
    assert store_a.state.releases[release_id][1] == store_b.state.releases[release_id][1]


def test_the_release_serves_the_default_session_at_the_sequence_it_was_built_at() -> None:
    backend, writer = populated()
    store, _ = build(backend)
    x = backend.tables.visible_seq()
    release = store.open(store.releases()[0])
    assert release is not None
    m = release.manifest
    assert (m.format, m.session, m.seq) == (FORMAT, S2.isoformat(), x)
    row = release.read("session").to_pylist()[0]
    live = resolve_session(StoreReader(backend), None)
    assert row["date"] == S2.isoformat() and row["complete"] is True and live.date == S2
    assert "bars/1d" in {i.table for i in m.inputs}
    assert writer is not None


def test_the_session_record_has_fixed_columns_and_no_newer() -> None:
    backend, _ = populated()
    session = resolve_session(StoreReader(backend), None)
    frame = session_frame(session)
    assert tuple(frame.columns) == SESSION_COLUMNS and "newer" not in SESSION_COLUMNS
    assert len(frame) == 1 and frame["date"].iloc[0] == S2.isoformat()
    assert frame.equals(session_frame(resolve_session(StoreReader(backend), None)))


class Flaky(StoreReader):
    """A reader whose pinned reads lose a version ``failures`` times."""

    def __init__(self, backend: MemoryBackend, failures: int) -> None:
        super().__init__(backend)
        self.failures = failures
        self.seen: list[int] = []

    def pinned(self, seq: int) -> StoreReader:
        self.seen.append(seq)
        if self.failures > 0:
            self.failures -= 1
            raise StaleSnapshotError("a version the build needed was replaced")
        return super().pinned(seq)


def test_a_stale_pin_restarts_the_build_and_after_three_tries_gives_up() -> None:
    backend, _ = populated()
    store = MemoryReleaseStore(backend.tables)
    once = Flaky(backend, 1)
    manifest = build_release(once, store, "abc")
    assert len(once.seen) == 2 and manifest.session == S2.isoformat()
    never = Flaky(backend, 99)
    with pytest.raises(StaleSnapshotError):
        build_release(never, MemoryReleaseStore(backend.tables), "abc")
    assert len(never.seen) == MAX_TRIES
    assert backend.tables.pins().keys() <= {f"release-{manifest.release_id}"}  # no pin left behind
