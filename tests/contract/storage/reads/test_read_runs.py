"""Storage contract, ``read_runs`` (ADR 0064, ADR 0022): several runs of one partition in one read
equal ``[read_run(...)]`` per request, whichever backend and however each file was written, and
the batch is read at one commit sequence (never a mix of versions)."""

from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from algotrade.storage.backends import local, partial_reads
from algotrade.storage.backends.arrow import parquet_bytes
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.backends.runs.run_selection import StaleSnapshotError
from algotrade.storage.tables.interfaces import Backend, RunRead
from algotrade.storage.tables.readers import StoreReader
from tests.helpers.stored_frames import T0, stamped

D1, D2 = date(2026, 10, 1), date(2026, 10, 2)
TABLE = "rollups/instrument/a@v1"
SCREEN = "results/rule_screen"
AT = T0 + timedelta(minutes=30)
IDS = [f"EQ:{c}" for c in "ABCDEFGH"]


@pytest.fixture(params=["memory", "local"])
def backend(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Backend]:
    yield MemoryBackend() if request.param == "memory" else LocalBackend(tmp_path / "data")


def publish(
    backend: Backend, run: str, ids: list[str], value: float = 1.0, day: date = D1, **extra: str
) -> int:
    rows = [{"instrument_id": i, "value": value + n, **extra} for n, i in enumerate(ids)]
    backend.tables.write(TABLE, day, run, stamped(rows, day, run), pending=True)
    backend.tables.commit_run(run, AT)
    return backend.tables.visible_seq()


def screen_rows(ids: list[str]) -> list[dict[str, object]]:
    return [
        {"instrument_id": i, "user_id": "u", "config_id": "c", "config_hash": "h",
         "decision": "PASS", "rank": n + 1, "score": 1.0 / (n + 1)}
        for n, i in enumerate(ids)
    ]  # fmt: skip


def publish_screen(backend: Backend, run: str, ids: list[str], day: date = D1) -> None:
    backend.tables.write(SCREEN, day, run, stamped(screen_rows(ids), day, run), pending=True)
    backend.tables.commit_run(run, AT)


def first(frame: pd.DataFrame | None) -> float:
    assert frame is not None
    return float(frame["value"].iloc[0])


def same(
    backend: Backend, table: str, runs: list[RunRead], day: date = D1, own: str | None = None
) -> dict[str, pd.DataFrame | None]:
    """``read_runs`` checked against ``read_run`` per request; the batch's answer."""
    got = backend.tables.read_runs(table, day, runs, own_run=own)
    assert list(got) == [r.run_id for r in runs]  # request order
    for one in runs:
        want = backend.tables.read_run(
            table, day, one.run_id, own_run=own, columns=one.columns, instruments=one.instruments
        )
        if want is None:
            assert got[one.run_id] is None, one
        else:
            pd.testing.assert_frame_equal(got[one.run_id], want)  # type: ignore[arg-type]
    return got


def test_the_batch_equals_read_run_per_request_with_columns_and_instruments(
    backend: Backend,
) -> None:
    publish(backend, "r1", IDS[:5], extra="x")
    publish(backend, "r2", IDS[3:], 10.0, extra="y")
    publish(backend, "r3", IDS[:2], 20.0)
    runs = [
        RunRead("r2", ["value"], ["EQ:E", "EQ:A"]),
        RunRead("r1"),
        RunRead("r3", None, ["EQ:B"]),
        RunRead("r3b"),  # absent from the index
    ]
    got = same(backend, TABLE, runs)
    assert got["r3b"] is None
    assert list(got["r2"]["instrument_id"]) == ["EQ:E"]  # type: ignore[index]


def test_every_request_filter_combination_agrees_with_read_run(backend: Backend) -> None:
    publish(backend, "r1", IDS)
    publish(backend, "r2", IDS[2:6], 5.0)
    for ids in (None, [], ["EQ:Z"], ["EQ:C"], ["EQ:H", "EQ:A", "EQ:D"]):
        for columns in (None, ["value"], []):
            same(backend, TABLE, [RunRead("r1", columns, ids), RunRead("r2", None, ids)])
    same(backend, TABLE, [RunRead("r1", None, ["EQ:C"]), RunRead("r2")])  # mixed filter / none


def test_a_run_absent_from_the_index_or_the_day_gives_none(backend: Backend) -> None:
    publish(backend, "r1", IDS[:2])
    got = same(backend, TABLE, [RunRead("nope"), RunRead("r1")])
    assert got["nope"] is None and got["r1"] is not None
    assert backend.tables.read_runs(TABLE, D2, [RunRead("r1")]) == {"r1": None}
    assert backend.tables.read_runs("rollups/instrument/none@v1", D1, [RunRead("r1")]) == {
        "r1": None
    }
    assert backend.tables.read_runs(TABLE, D1, []) == {}


def test_a_repeated_run_id_is_refused(backend: Backend) -> None:
    publish(backend, "r1", IDS[:2])
    with pytest.raises(ValueError, match="twice"):
        backend.tables.read_runs(TABLE, D1, [RunRead("r1"), RunRead("r1", ["value"])])


def test_an_own_pending_run_is_seen_only_by_its_owner(backend: Backend) -> None:
    publish(backend, "r1", IDS[:2])
    rows = [{"instrument_id": "EQ:Q", "value": 9.0}]
    backend.tables.write(TABLE, D1, "mine", stamped(rows, D1, "mine"), pending=True)
    runs = [RunRead("mine"), RunRead("r1")]
    assert same(backend, TABLE, runs)["mine"] is None
    assert same(backend, TABLE, runs, own="mine")["mine"] is not None
    reader = StoreReader(backend, own_run="mine")
    assert reader.read_runs(TABLE, D1, runs)["mine"] is not None


def test_upto_is_honoured_and_a_later_run_is_hidden_not_stale(backend: Backend) -> None:
    first = publish(backend, "r1", IDS[:2])
    second = publish(backend, "r2", IDS[2:4])
    runs = [RunRead("r1"), RunRead("r2")]
    early = backend.tables.read_runs(TABLE, D1, runs, upto=first)
    assert early["r2"] is None and early["r1"] is not None
    late = backend.tables.read_runs(TABLE, D1, runs, upto=second)
    assert late["r1"] is not None and late["r2"] is not None
    assert StoreReader(backend).pinned(first).read_runs(TABLE, D1, runs)["r2"] is None


def test_a_pinned_batch_is_one_version_after_a_recommit_and_stale_without_a_pin(
    backend: Backend,
) -> None:
    publish(backend, "r2", IDS[:2], 1.0)
    x = publish(backend, "r1", IDS[:2], 1.0)
    backend.tables.pin("release-a", x)
    publish(backend, "r1", IDS[:2], 2.0)  # r1 recommitted; r2 untouched
    runs = [RunRead("r1"), RunRead("r2")]
    pinned = backend.tables.read_runs(TABLE, D1, runs, upto=x)
    assert first(pinned["r1"]) == 1.0
    assert first(backend.tables.read_runs(TABLE, D1, runs)["r1"]) == 2.0
    backend.tables.unpin("release-a")
    publish(backend, "r1", IDS[:2], 3.0)
    publish(backend, "r1", IDS[:2], 4.0)
    with pytest.raises(StaleSnapshotError):
        backend.tables.read_runs(TABLE, D1, runs, upto=x)


def raced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, commits: int
) -> tuple[list[int], dict[str, float]]:
    """A batch whose index was resolved, then ``commits`` recommits of both runs land before its
    files are read: the calls the scan took and each run's value in the answer."""
    store = LocalBackend(tmp_path / "data")
    publish(store, "r1", IDS[:2], 1.0)
    publish(store, "r2", IDS[:2], 1.0)
    real, calls = partial_reads.read_runs_files, []

    def commit_then_read(files: dict[str, Path], runs: list[RunRead]) -> object:
        calls.append(1)
        if len(calls) == 1:  # after the index was resolved, before the files were read
            for n in range(commits):
                publish(store, "r1", IDS[:2], 2.0 + n)
                publish(store, "r2", IDS[:2], 2.0 + n)
        return real(files, runs)

    monkeypatch.setattr(local, "read_runs_files", commit_then_read)
    got = store.tables.read_runs(TABLE, D1, [RunRead("r1"), RunRead("r2")])
    return calls, {k: first(v) for k, v in got.items()}


def test_a_commit_between_resolve_and_read_gives_the_resolved_version_for_every_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls, values = raced(tmp_path, monkeypatch, commits=1)  # the old versions are still kept
    assert len(calls) == 1 and values == {"r1": 1.0, "r2": 1.0}


def test_a_version_dropped_between_resolve_and_read_retries_the_whole_batch_fresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls, values = raced(tmp_path, monkeypatch, commits=4)  # the resolved versions are gone
    assert len(calls) == 2  # one retry of the batch, at a fresh sequence
    assert values == {"r1": 5.0, "r2": 5.0}  # both at the newest: never one old, one new


def test_files_of_every_layout_agree_with_read_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An older one-group file, a clustered file (#855) and a sorted, row-capped one (#857)
    in one partition."""
    store = LocalBackend(tmp_path / "data")
    with monkeypatch.context() as old:
        old.setattr(local, "table_parquet_bytes", lambda _t, data: parquet_bytes(data))
        publish_screen(store, "old", IDS[::-1])  # unsorted, one row group
    publish_screen(store, "new", IDS[2:] + IDS[:2])  # sorted by instrument, row-capped groups
    publish_screen(store, "wide", [f"EQ:{n:05d}" for n in range(30_000)])  # several groups
    runs = [
        RunRead("new", None, ["EQ:A", "EQ:F"]),
        RunRead("old", ["score"], ["EQ:H", "EQ:B", "EQ:Z"]),
        RunRead("wide", ["rank"], ["EQ:00007", "EQ:29999"]),
    ]
    got = same(store, SCREEN, runs)
    assert list(got["wide"]["instrument_id"]) == ["EQ:00007", "EQ:29999"]  # type: ignore[index]
