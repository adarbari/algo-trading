"""Storage contract, atomic runs (ADR 0022): a run's pending writes become visible in every
partition at once when it commits, never in part; an aborted or crashed run shows nothing."""

import threading
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from algotrade.storage.backends import local_index
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.interfaces import Backend
from algotrade.storage.tables.result_writer import ResultWriter
from tests.helpers.stored_frames import T0, stamped

D1, D2 = date(2026, 10, 1), date(2026, 10, 2)
A, B = "rollups/instrument/a@v1", "rollups/instrument/b@v1"
EVENTS = "events/dividend"
COMMIT = T0 + timedelta(minutes=30)


@pytest.fixture(params=["memory", "local"])
def backend(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Backend]:
    yield MemoryBackend() if request.param == "memory" else LocalBackend(tmp_path / "data")


def value(run: str, v: float, day: date = D1, at: object = T0) -> pd.DataFrame:
    return stamped([{"instrument_id": "EQ:A", "value": v}], day, run, at)  # type: ignore[arg-type]


def values(backend: Backend, table: str, day: date = D1, **kw: object) -> list[float] | None:
    frame = backend.tables.read(table, day, **kw)  # type: ignore[arg-type]
    return None if frame is None else list(frame["value"])


def pending_two_tables(backend: Backend, run: str = "r1", v: float = 1.0) -> None:
    backend.tables.write(A, D1, run, value(run, v), pending=True)
    backend.tables.write(B, D1, run, value(run, v + 1), pending=True)


def test_pending_writes_are_invisible_until_the_commit(backend: Backend) -> None:
    pending_two_tables(backend)
    assert values(backend, A) is None and values(backend, B) is None
    assert backend.tables.dates(A) == [] and backend.tables.names() == []
    assert backend.tables.read_range(A, D1, D2) is None
    assert backend.tables.pending_runs() == ["r1"]
    # the writing run reads its own writes
    assert values(backend, A, own_run="r1") == [1.0]
    assert backend.tables.dates(A, own_run="r1") == [D1]
    assert backend.tables.names(own_run="r1") == [A, B]
    own = backend.tables.read_range(B, D1, D2, own_run="r1")
    assert own is not None and list(own["value"]) == [2.0]
    assert backend.tables.commit_run("r1", COMMIT) == 2
    assert values(backend, A) == [1.0] and values(backend, B) == [2.0]
    assert backend.tables.pending_runs() == []


def test_a_failed_run_publishes_nothing(backend: Backend) -> None:
    backend.tables.write(A, D1, "old", value("old", 0.0))
    backend.tables.write(B, D1, "old", value("old", 0.0))
    backend.tables.write(A, D1, "r1", value("r1", 1.0), pending=True)  # then table B fails
    assert backend.tables.abort_run("r1") == 1
    assert values(backend, A) == [0.0] and values(backend, B) == [0.0]
    assert backend.tables.pending_runs() == []
    assert backend.tables.commit_run("r1", COMMIT) == 0  # nothing left to commit
    assert values(backend, A) == [0.0]
    if isinstance(backend, LocalBackend):
        directory = backend.root / "tables" / A / f"date={D1.isoformat()}"
        assert sorted(p.name for p in directory.glob("*.parquet")) == ["run=old.parquet"]


def test_as_of_sees_a_run_from_its_commit_time(backend: Backend) -> None:
    pending_two_tables(backend)
    backend.tables.commit_run("r1", COMMIT)
    assert values(backend, A, as_of=T0) is None  # written at T0, but not committed yet
    assert values(backend, A, as_of=COMMIT) == [1.0]
    assert values(backend, B, as_of=COMMIT) == [2.0]
    frame = backend.tables.read(A, D1)
    assert frame is not None and frame["knowledge_ts"].iloc[0] == pd.Timestamp(T0)


def test_merge_and_restating_runs_commit_like_plain_writes(backend: Backend) -> None:
    def div(iid: str, amount: float, run: str, at: object) -> pd.DataFrame:
        row = {"instrument_id": iid, "ts": pd.Timestamp(D1, tz="UTC"), "cash_amount": amount}
        return stamped([row], D1, run, at)  # type: ignore[arg-type]

    backend.tables.write(EVENTS, D1, "a", div("EQ:A", 1.0, "a", T0), pending=True)
    backend.tables.commit_run("a", T0)
    backend.tables.write(EVENTS, D1, "b", div("EQ:B", 2.0, "b", COMMIT), pending=True)
    backend.tables.commit_run("b", COMMIT)
    merged = backend.tables.read(EVENTS, D1)
    assert merged is not None and sorted(merged["instrument_id"]) == ["EQ:A", "EQ:B"]
    later = COMMIT + timedelta(hours=1)
    backend.tables.write(EVENTS, D1, "m", div("EQ:C", 3.0, "m", later), True, pending=True)
    restated = backend.tables.read(EVENTS, D1)
    assert restated is not None and sorted(restated["instrument_id"]) == ["EQ:A", "EQ:B"]
    backend.tables.commit_run("m", later)
    restated = backend.tables.read(EVENTS, D1)
    assert restated is not None and list(restated["instrument_id"]) == ["EQ:C"]
    before = backend.tables.read(EVENTS, D1, as_of=COMMIT)
    assert before is not None and len(before) == 2


def test_a_resumed_run_replaces_its_rows_at_its_commit(backend: Backend) -> None:
    backend.tables.write(A, D1, "r1", value("r1", 1.0), pending=True)
    backend.tables.commit_run("r1", T0)
    backend.tables.write(A, D1, "r1", value("r1", 5.0, at=COMMIT), pending=True)
    assert values(backend, A) == [1.0]  # the committed version until the resumed run commits
    assert values(backend, A, own_run="r1") == [5.0]
    backend.tables.commit_run("r1", COMMIT)
    assert values(backend, A) == [5.0]
    backend.tables.write(A, D1, "r1", value("r1", 7.0, at=COMMIT), pending=True)
    backend.tables.commit_run("r1", COMMIT)
    assert values(backend, A) == [7.0]
    if isinstance(backend, LocalBackend):
        directory = backend.root / "tables" / A / f"date={D1.isoformat()}"
        assert len(list(directory.glob("*.parquet"))) == 2  # the version and the one before


def test_an_empty_pending_write_creates_the_partition_without_rows(backend: Backend) -> None:
    empty = value("r1", 1.0).iloc[0:0]
    backend.tables.write(A, D1, "r1", empty, pending=True)
    assert backend.tables.dates(A) == []
    backend.tables.commit_run("r1", COMMIT)
    assert backend.tables.dates(A) == [D1]
    assert values(backend, A) is None


def test_a_crash_before_the_commit_leaves_nothing_visible(backend: Backend, tmp_path: Path) -> None:
    pending_two_tables(backend)
    restarted = LocalBackend(tmp_path / "data") if isinstance(backend, LocalBackend) else backend
    assert restarted.tables.recover_runs() == []  # no commit had started
    assert values(restarted, A) is None and values(restarted, B) is None
    assert restarted.tables.pending_runs() == ["r1"]
    assert restarted.tables.abort_run("r1") == 2
    assert restarted.tables.pending_runs() == []
    assert values(restarted, A, own_run="r1") is None
    if isinstance(restarted, LocalBackend):
        assert not list((tmp_path / "data" / "tables").glob("**/run=r1*.parquet"))


def test_retention_aborts_pending_runs_last_written_before_the_cutoff(backend: Backend) -> None:
    pending_two_tables(backend)
    assert backend.tables.purge_pending_before(T0 - timedelta(days=3650)) == 0
    assert backend.tables.purge_pending_before(pd.Timestamp.now(tz="UTC") + timedelta(1)) == 1
    assert backend.tables.pending_runs() == []


def test_a_crash_inside_the_commit_is_completed_by_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "data"
    backend = LocalBackend(root)
    backend.tables.write(A, D1, "old", value("old", 0.0))
    backend.tables.write(B, D1, "old", value("old", 0.0))
    pending_two_tables(backend)
    real, calls = local_index.write_index, []

    def crash_on_second(directory: Path, entries: dict[str, object]) -> None:
        calls.append(directory)
        if len(calls) == 2:
            raise OSError("power cut")
        real(directory, entries)  # type: ignore[arg-type]

    monkeypatch.setattr(local_index, "write_index", crash_on_second)
    with pytest.raises(OSError):
        backend.tables.commit_run("r1", COMMIT)
    monkeypatch.setattr(local_index, "write_index", real)
    restarted = LocalBackend(root)
    # A's index already holds r1, but its commit was never published: neither table shows it
    assert values(restarted, A) == [0.0] and values(restarted, B) == [0.0]
    assert restarted.tables.recover_runs() == ["r1"]
    assert values(restarted, A) == [1.0] and values(restarted, B) == [2.0]
    assert restarted.tables.recover_runs() == []  # idempotent
    assert restarted.tables.pending_runs() == []


def test_the_next_commit_completes_an_interrupted_one_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = LocalBackend(tmp_path / "data")
    pending_two_tables(backend)
    real = local_index.write_index

    def crash(directory: Path, entries: dict[str, object]) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(local_index, "write_index", crash)
    with pytest.raises(OSError):
        backend.tables.commit_run("r1", COMMIT)
    monkeypatch.setattr(local_index, "write_index", real)
    backend.tables.write(A, D2, "r2", value("r2", 9.0, D2), pending=True)
    backend.tables.commit_run("r2", COMMIT)
    assert values(backend, A) == [1.0] and values(backend, B) == [2.0]
    assert values(backend, A, D2) == [9.0]
    assert backend.tables.abort_run("r1") == 0  # completed, so nothing to abort


DAYS = [D1 + timedelta(days=i) for i in range(5)]


def _commit_many(backend: Backend, runs: int, same_run: bool) -> None:
    for k in range(1, runs + 1):
        run = "resumed" if same_run else f"r{k:03d}"
        for day in DAYS:
            at = T0 + timedelta(seconds=k)
            backend.tables.write(A, day, run, value(run, float(k), day, at), pending=True)
        backend.tables.commit_run(run, T0 + timedelta(seconds=k))


@pytest.mark.parametrize("same_run", [False, True], ids=["new-runs", "resumed-run"])
def test_a_concurrent_reader_sees_a_commit_whole_or_not_at_all(
    backend: Backend, same_run: bool
) -> None:
    _commit_many(backend, 1, same_run)
    seen: list[tuple[int, set[float]]] = []
    done = threading.Event()

    def reader() -> None:
        while not done.is_set():
            frame = backend.tables.read_range(A, DAYS[0], DAYS[-1])
            seen.append((0, set()) if frame is None else (len(frame), set(frame["value"])))

    thread = threading.Thread(target=reader)
    thread.start()
    try:
        _commit_many(backend, 40, same_run)
    finally:
        done.set()
        thread.join()
    torn = [s for s in seen if s[0] != len(DAYS) or len(s[1]) != 1]
    assert seen and not torn, torn[:3]


def test_result_runs_publish_together_or_not_at_all(backend: Backend) -> None:
    writer = ResultWriter(backend)
    with pytest.raises(RuntimeError), writer.publishing("bt1", COMMIT):
        writer.write_result("equity", D1, "bt1", value("bt1", 1.0), pending=True)
        raise RuntimeError("trades frame failed")
    assert backend.tables.read("results/equity", D1) is None
    assert backend.tables.pending_runs() == []
    with writer.publishing("bt2", COMMIT):
        writer.write_result("equity", D1, "bt2", value("bt2", 1.0), pending=True)
        writer.write_result("trades", D1, "bt2", value("bt2", 2.0), pending=True)
        assert backend.tables.read("results/trades", D1) is None
    assert values(backend, "results/equity") == [1.0]
    assert values(backend, "results/trades") == [2.0]
