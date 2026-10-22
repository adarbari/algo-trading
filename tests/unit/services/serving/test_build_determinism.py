"""The release build (ADR 0077): the session record at one pinned sequence, written so that two
builds of the same store are byte for byte equal, restarted when a version it needs is lost."""

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from algotrade.data import StoreReader
from algotrade.services.read.session import Session, resolve_session
from algotrade.services.serving import build as build_module
from algotrade.services.serving.build import (
    FORMAT,
    MAX_TRIES,
    SESSION_COLUMNS,
    build_release,
    session_frame,
)
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.backends.release.interfaces import ReleaseInvalidError
from algotrade.storage.backends.release.memory import MemoryReleaseStore
from algotrade.storage.backends.runs.run_selection import StaleSnapshotError
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.rollup_store import write_rows
from tests.helpers.stored_frames import stamped

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


def test_a_stale_pin_restarts_the_build_and_after_three_tries_gives_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend, _ = populated()
    reads: list[int] = []
    real = build_module.resolve_session

    def lose(times: int) -> object:
        def resolve(reader: StoreReader, requested: date | None) -> Session:
            reads.append(1)
            if len(reads) <= times:
                raise StaleSnapshotError("a version the build needed was replaced")
            return real(reader, requested)

        return resolve

    monkeypatch.setattr(build_module, "resolve_session", lose(1))
    manifest = build_release(StoreReader(backend), MemoryReleaseStore(backend.tables), "abc")
    assert len(reads) == 2 and manifest.session == S2.isoformat()
    reads.clear()
    monkeypatch.setattr(build_module, "resolve_session", lose(99))
    with pytest.raises(StaleSnapshotError):
        build_release(StoreReader(backend), MemoryReleaseStore(backend.tables), "abc")
    assert len(reads) == MAX_TRIES
    assert backend.tables.pins().keys() <= {f"release-{manifest.release_id}"}  # none left behind


def test_a_session_completed_after_the_pin_is_never_named_by_the_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The nightly commits S+1's tables then saves its COMPLETE record: both after X was taken.
    The run records are read before X, so the build still answers S, with S's tables."""
    backend, _ = populated()
    day = date(2026, 10, 3)
    real = build_module.resolve_session

    def after_x(reader: StoreReader, requested: date | None) -> Session:
        bar = {"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}
        row = {"instrument_id": "EQ:AAA", "ts": pd.Timestamp(day, tz="UTC"), **bar}
        backend.tables.write(
            "bars/1d", day, "nightly-3", stamped([row], day, "nightly-3"), pending=True
        )
        backend.tables.commit_run("nightly-3", datetime(2026, 10, 3, 22, tzinfo=UTC))  # a commit
        started = datetime(day.year, day.month, day.day, 22, tzinfo=UTC)
        record = RunRecord(f"nightly-{day}", "nightly", day, started, RunStatus.COMPLETE, started)
        backend.runs.save(record)
        return real(reader, requested)

    monkeypatch.setattr(build_module, "resolve_session", after_x)
    store = MemoryReleaseStore(backend.tables)
    manifest = build_release(StoreReader(backend), store, "abc")
    assert manifest.session == S2.isoformat()
    assert resolve_session(StoreReader(backend), None).date == day  # live has moved on


def test_a_destructive_operation_during_the_reads_stops_the_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend, _ = populated()
    real = build_module.resolve_session

    def drop_midway(reader: StoreReader, requested: date | None) -> Session:
        found = real(reader, requested)
        backend.tables.drop("rollups/instrument/other@v1")  # between the reads and the draft
        return found

    monkeypatch.setattr(build_module, "resolve_session", drop_midway)
    store = MemoryReleaseStore(backend.tables)
    with pytest.raises(ReleaseInvalidError, match="epoch"):
        build_release(StoreReader(backend), store, "abc")
    assert backend.tables.pins() == {} and store.releases() == []
