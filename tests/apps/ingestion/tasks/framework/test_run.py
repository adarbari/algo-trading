"""``IngestRun``: raw save, id resolution, stamping, status rules and the failure path."""

from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from algotrade.data import StoreReader
from algotrade.storage.backends import local_index
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.framework.run import (
    IngestRun,
    NoResponseError,
    recover_unpublished,
    resumable_run,
    retryable_items,
    run_summary,
    stamp,
)
from algotrade_sources.framework.base import FetchRequest, Normalized
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.stored_frames import write_reference

DAY = date(2026, 10, 2)
NOW = datetime(2026, 10, 2, 22, tzinfo=UTC)
EVENTS = "events/split"  # a generic event table (no required known_from)


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


def test_resume_keeps_finished_items_and_retries_fetch_errors_and_stale_data() -> None:
    writer, reader, _ = store()
    ctx = task_ctx(writer, reader)
    with IngestRun(ctx, "demo", DAY, resume=True) as first:
        first.record_item("a", "OK")
        first.stage("t", "a", pd.DataFrame({"x": [1]}), "src")  # the scratch a resume needs
        first.fail("b", "timeout")
        first.fail("c", "old", kind="STALE_DATA")
    second = IngestRun(ctx, "demo", DAY, resume=True)
    assert second.run_id == first.run_id
    assert second.items == {"a": "OK"}  # FETCH_ERROR and STALE_DATA items are refetched
    with second:
        second.record_item("b", "OK")
        second.record_item("c", "OK")
    assert second.record.status is RunStatus.COMPLETE
    assert IngestRun(ctx, "demo", DAY, resume=True).items == {}  # complete: a fresh run


def test_a_resumed_run_cut_short_keeps_what_it_did_not_reach() -> None:
    writer, reader, _ = store()
    ctx = task_ctx(writer, reader)
    with IngestRun(ctx, "demo", DAY, resume=True) as first:
        first.record_item("a", "OK")
        first.stage("t", "a", pd.DataFrame({"x": [1]}), "src")
        first.fail("b", "old", kind="STALE_DATA")
        first.fail("c", "old", kind="STALE_DATA")
    with pytest.raises(RuntimeError), IngestRun(ctx, "demo", DAY, resume=True) as cut:
        assert cut.items == {"a": "OK"}  # b and c are to be refetched
        cut.record_item("b", "OK")
        raise RuntimeError("vendor down")  # before c
    saved = writer.load_run(first.run_id)
    assert saved is not None and saved.status is RunStatus.FAILED
    assert saved.items == {"a": "OK", "b": "OK", "c": "STALE_DATA: old"}  # c still counts
    resumed = resumable_run(writer, "demo", DAY)
    assert retryable_items(saved) == ["c"] and resumed is not None
    assert resumed.run_id == first.run_id  # the nightly and the next resume agree on the run
    assert IngestRun(ctx, "demo", DAY, resume=True).items == {"a": "OK", "b": "OK"}


def test_staging_publish_and_rewrite() -> None:
    writer, reader, _ = store()
    rows = [{"instrument_id": "EQ:B", "ts": pd.Timestamp(DAY, tz="UTC")}]
    later = datetime(2026, 10, 3, tzinfo=UTC)
    with IngestRun(task_ctx(writer, reader, lambda: NOW), "demo", DAY) as run:
        run.stage(EVENTS, "B", pd.DataFrame(rows), "fake")
        run.stage(EVENTS, "A", pd.DataFrame([{**rows[0], "instrument_id": "EQ:A"}]), "fake")
        assert run.publish(EVENTS) == 2
        assert run.publish("events/dividend") == 0  # nothing staged
    assert writer.staging.keys(run.run_id, EVENTS) == []  # complete: staging dropped
    stored = reader.table(EVENTS, DAY)
    assert stored is not None and list(stored["instrument_id"]) == ["EQ:A", "EQ:B"]
    with IngestRun(task_ctx(writer, reader, lambda: later), "fix", DAY) as fix:
        fix.rewrite(EVENTS, DAY, stored)
    again = reader.table(EVENTS, DAY)
    assert again is not None and set(again["run_id"]) == {fix.run_id}
    assert set(again["source"]) == {"fake"}  # only knowledge_ts and run_id change


@pytest.mark.parametrize("kind", ["memory", "local"])
def test_staging_is_kept_while_a_resume_needs_it(kind: str, tmp_path: Path) -> None:
    backend = MemoryBackend() if kind == "memory" else LocalBackend(tmp_path)
    writer, reader = StoreWriter(backend), StoreReader(backend)
    ctx = task_ctx(writer, reader, lambda: NOW)
    row = pd.DataFrame([{"instrument_id": "EQ:A", "ts": pd.Timestamp(DAY, tz="UTC")}])
    with pytest.raises(RuntimeError), IngestRun(ctx, "demo", DAY, resume=True) as crashed:
        crashed.stage(EVENTS, "A", row, "fake")
        crashed.record_item("a", "OK")
        raise RuntimeError("vendor down")
    assert crashed.record.status is RunStatus.FAILED
    assert writer.staging.keys(crashed.run_id, EVENTS) == ["A"]  # FAILED: kept
    with IngestRun(ctx, "demo", DAY, resume=True) as retry:
        retry.stage(EVENTS, "B", row.assign(instrument_id="EQ:B"), "fake")
        retry.fail("b", "timeout")
        assert retry.retryable() == ["b"]
        assert retry.publish(EVENTS) == 2  # the crashed run's scratch is still there
    assert retry.run_id == crashed.run_id and retry.record.status is RunStatus.PARTIAL
    assert writer.staging.keys(retry.run_id, EVENTS) == ["A", "B"]  # FETCH_ERROR left: kept
    with IngestRun(ctx, "demo", DAY, resume=True) as last:
        last.record_item("b", "OK")
        assert last.publish(EVENTS) == 2
    assert last.run_id == crashed.run_id and last.record.status is RunStatus.COMPLETE
    assert writer.staging.keys(last.run_id, EVENTS) == []  # nothing left to retry: dropped
    stored = reader.table(EVENTS, DAY)
    assert stored is not None and sorted(stored["instrument_id"]) == ["EQ:A", "EQ:B"]


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


# ---------------------------------------------------------------------- atomic publication

A, B = "rollups/instrument/a@v1", "rollups/instrument/b@v1"


def _rows(value: float) -> pd.DataFrame:
    return pd.DataFrame({"instrument_id": ["EQ:A"], "value": [value]})


def test_a_run_publishes_every_table_when_it_finishes() -> None:
    writer, reader, backend = store()
    with IngestRun(task_ctx(writer, reader, lambda: NOW), "demo", DAY) as run:
        run.write(A, _rows(1.0), "test")
        run.write(B, _rows(2.0), "test")
        assert reader.table(A, DAY) is None  # not before the run finishes
        own = run.reader.table(A, DAY)  # the run reads what it wrote
        assert own is not None and list(own["value"]) == [1.0]
        assert writer.load_run(run.run_id).status is RunStatus.RUNNING  # type: ignore[union-attr]
    assert reader.table(A, DAY) is not None and reader.table(B, DAY) is not None
    assert backend.tables.pending_runs() == []


def test_a_failed_run_publishes_nothing() -> None:
    writer, reader, backend = store()
    ctx = task_ctx(writer, reader, lambda: NOW)
    with pytest.raises(RuntimeError), IngestRun(ctx, "demo", DAY) as run:
        run.write(A, _rows(1.0), "test")
        raise RuntimeError("table b failed")
    assert reader.table(A, DAY) is None and reader.dates(A) == []
    assert backend.tables.pending_runs() == []
    assert writer.load_run(run.run_id).status is RunStatus.FAILED  # type: ignore[union-attr]
    with IngestRun(task_ctx(writer, reader, lambda: NOW), "explicit", DAY) as run:
        run.write(A, _rows(1.0), "test")
        run.failed("every step failed")
    assert reader.table(A, DAY) is None


def test_a_partial_run_still_publishes() -> None:
    writer, reader, _ = store()
    with IngestRun(task_ctx(writer, reader, lambda: NOW), "demo", DAY) as run:
        run.write(A, _rows(1.0), "test")
        run.partial("one source missing")
    assert run.record.status is RunStatus.PARTIAL and reader.table(A, DAY) is not None


def test_recovery_drops_what_a_crashed_run_wrote() -> None:
    writer, reader, backend = store()
    crashed = IngestRun(task_ctx(writer, reader, lambda: NOW), "demo", DAY).__enter__()
    crashed.write(A, _rows(1.0), "test")  # the process dies here: no __exit__
    backend.tables.write(B, DAY, "service-run", stamp(_rows(2.0), DAY, NOW, "t", "s"), pending=True)
    assert recover_unpublished(writer, NOW) == {"completed": [], "dropped": [crashed.run_id]}
    assert backend.tables.pending_runs() == ["service-run"]  # no record: left to retention
    assert reader.table(A, DAY) is None


def test_recovery_completes_a_commit_a_crash_interrupted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = LocalBackend(tmp_path / "data")
    writer, reader = StoreWriter(backend), StoreReader(backend)
    real = local_index.write_index

    def crash(directory: Path, entries: dict[str, object]) -> None:
        raise OSError("power cut")

    ctx = task_ctx(writer, reader, lambda: NOW)
    with pytest.raises(OSError), IngestRun(ctx, "demo", DAY) as run:
        run.write(A, _rows(1.0), "test")
        run.write(B, _rows(2.0), "test")
        monkeypatch.setattr(local_index, "write_index", crash)
    monkeypatch.setattr(local_index, "write_index", real)
    record = writer.load_run(run.run_id)
    assert record is not None and record.status is RunStatus.FAILED
    assert "commit failed" in record.stats["error"]
    assert reader.table(A, DAY) is None
    restarted = StoreWriter(LocalBackend(tmp_path / "data"))
    assert recover_unpublished(restarted, NOW) == {"completed": [run.run_id], "dropped": []}
    assert reader.table(A, DAY) is not None and reader.table(B, DAY) is not None
    record = restarted.load_run(run.run_id)
    assert record is not None and record.status is RunStatus.PARTIAL
    assert "recovered" in record.stats
