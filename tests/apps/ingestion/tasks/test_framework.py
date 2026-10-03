"""``IngestRun``: raw save, id resolution, stamping, status rules and the failure path."""

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from algotrade.data import StoreReader
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.sources.base import FetchRequest, Normalized
from algotrade_ingestion.tasks.framework import (
    IngestRun,
    NoResponseError,
    run_summary,
    stamp,
)
from tests.ingest_helpers import task_ctx
from tests.storage_helpers import write_reference

DAY = date(2026, 10, 2)
NOW = datetime(2026, 10, 2, 22, tzinfo=UTC)
EVENTS = "events/earnings"


class FakeSource:
    name, dataset = "fake", "calendar"

    def __init__(self, payloads: dict[str, bytes | None]) -> None:
        self.payloads = payloads

    def fetch(self, request: FetchRequest) -> bytes | None:
        return self.payloads.get(request.key)

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        symbols = payload.decode().split(",")
        frame = pd.DataFrame({"symbol": symbols, "ts": pd.Timestamp(DAY, tz="UTC")})
        return Normalized(session_date=DAY, tables={EVENTS: frame})


def store() -> tuple[StoreWriter, StoreReader, MemoryBackend]:
    backend = MemoryBackend()
    return StoreWriter(backend), StoreReader(backend), backend


def test_fetch_saves_raw_resolves_ids_and_stamps() -> None:
    writer, reader, backend = store()
    write_reference(writer, DAY, {"AAPL": "EQ:BBG000B9XRY4"})
    source = FakeSource({"k": b"AAPL,ZZZ"})
    with IngestRun(task_ctx(writer, reader, lambda: NOW), "demo", DAY) as run:
        normalized = run.fetch(source, FetchRequest("k", session_date=DAY))
        assert normalized is not None
        frame = run.resolve(normalized.tables[EVENTS])
        run.write(EVENTS, frame, source.name)
    assert backend.raw.get("fake", "calendar", DAY, run.run_id, "k") == b"AAPL,ZZZ"
    stored = reader.table(EVENTS, DAY)
    assert stored is not None
    assert list(stored["instrument_id"]) == ["EQ:BBG000B9XRY4", "EQ:ZZZ"]
    assert set(stored["run_id"]) == {run.run_id} and set(stored["source"]) == {"fake"}
    assert set(stored["session_date"]) == {DAY}
    assert run.record.status is RunStatus.COMPLETE
    assert run.record.stats["unresolved"] == 1  # ZZZ: not in the reference
    saved = writer.runs_for("demo", DAY)
    assert [r.run_id for r in saved] == [run.run_id] and saved[0].finished_at == NOW


def test_missing_payload_raises_no_response() -> None:
    writer, reader, _ = store()
    run = IngestRun(task_ctx(writer, reader), "demo", DAY)
    with pytest.raises(NoResponseError, match="fake gone: no response"):
        run.fetch(FakeSource({}), FetchRequest("gone"))


def test_item_failures_make_the_run_partial() -> None:
    writer, reader, _ = store()

    def boom() -> str:
        raise ValueError("bad payload")

    with IngestRun(task_ctx(writer, reader), "demo", DAY) as run:
        assert run.attempt("a", lambda: "OK") == "OK"
        assert run.attempt("b", boom) == "FETCH_ERROR: bad payload"
        run.fail("c", "old chain", kind="STALE_DATA")
    assert run.record.status is RunStatus.PARTIAL
    assert run.failures() == ["b: bad payload", "c: old chain"]
    assert run.counts() == {"OK": 1, "FETCH_ERROR": 1, "STALE_DATA": 1}


def test_explicit_partial_is_recorded() -> None:
    writer, reader, _ = store()
    with IngestRun(task_ctx(writer, reader), "demo", DAY) as run:
        run.record_item("a", "OK")
        run.partial("suspicious volume")
    assert run.record.status is RunStatus.PARTIAL
    assert run.record.stats["partial"] == ["suspicious volume"]
    assert run_summary(run.record)["status"] == RunStatus.PARTIAL


def test_a_fatal_error_saves_a_failed_record_then_reraises() -> None:
    writer, reader, _ = store()
    with (
        pytest.raises(RuntimeError, match="vendor down"),
        IngestRun(task_ctx(writer, reader), "demo", DAY),
    ):
        raise RuntimeError("vendor down")
    saved = writer.runs_for("demo", DAY)
    assert [r.status for r in saved] == [RunStatus.FAILED]
    assert saved[0].stats["error"] == "RuntimeError: vendor down"


def test_resume_keeps_finished_items_and_retries_fetch_errors() -> None:
    writer, reader, _ = store()
    ctx = task_ctx(writer, reader)
    with IngestRun(ctx, "demo", DAY, resume=True) as first:
        first.record_item("a", "OK")
        first.fail("b", "timeout")
        first.fail("c", "old", kind="STALE_DATA")
    second = IngestRun(ctx, "demo", DAY, resume=True)
    assert second.run_id == first.run_id
    assert second.items == {"a": "OK", "c": "STALE_DATA: old"}
    with second:
        second.items.pop("c")
        second.record_item("b", "OK")
    assert second.record.status is RunStatus.COMPLETE
    assert IngestRun(ctx, "demo", DAY, resume=True).items == {}  # complete: a fresh run


def test_staging_publish_and_rewrite() -> None:
    writer, reader, _ = store()
    rows = [{"instrument_id": "EQ:B", "ts": pd.Timestamp(DAY, tz="UTC")}]
    later = datetime(2026, 10, 3, tzinfo=UTC)
    with IngestRun(task_ctx(writer, reader, lambda: NOW), "demo", DAY) as run:
        run.stage(EVENTS, "B", pd.DataFrame(rows), "fake")
        run.stage(EVENTS, "A", pd.DataFrame([{**rows[0], "instrument_id": "EQ:A"}]), "fake")
        assert run.publish(EVENTS) == 2
        assert run.publish("events/split") == 0  # nothing staged
        run.clear_staging()
    stored = reader.table(EVENTS, DAY)
    assert stored is not None and list(stored["instrument_id"]) == ["EQ:A", "EQ:B"]
    with IngestRun(task_ctx(writer, reader, lambda: later), "fix", DAY) as fix:
        fix.rewrite(EVENTS, DAY, stored)
    again = reader.table(EVENTS, DAY)
    assert again is not None and set(again["run_id"]) == {fix.run_id}
    assert set(again["source"]) == {"fake"}  # only knowledge_ts and run_id change


def test_unsaved_runs_write_no_record() -> None:
    writer, reader, _ = store()
    with IngestRun(task_ctx(writer, reader), "dry", DAY, save=False) as run:
        run.checkpoint()
    assert writer.runs_for("dry", DAY) == [] and run.record.status is RunStatus.COMPLETE


def test_resolvers_are_cached_per_reference_snapshot() -> None:
    writer, reader, _ = store()
    write_reference(writer, DAY, {"AAPL": "EQ:BBG000B9XRY4"})
    run = IngestRun(task_ctx(writer, reader), "demo", DAY)
    assert run.resolver() is run.resolver(date(2026, 10, 5))  # same snapshot
    frame = pd.DataFrame({"instrument_id": ["EQ:X"]})
    assert run.resolve(frame) is frame  # already resolved: passes through


def test_stamp_adds_point_in_time_columns() -> None:
    out = stamp(pd.DataFrame({"x": [1]}), DAY, NOW, "src", "r1")
    assert list(out.columns) == ["x", "session_date", "knowledge_ts", "source", "run_id"]
