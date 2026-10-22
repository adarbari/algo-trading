"""Storage contract, ``read_latest_runs`` (ADR 0029 amendment): the rows of each (user, config)'s
newest run of a partition, the same rows as ``read`` followed by the screen readers' latest-run
rule (``last_run_rows``) per group, decoding only those runs' files."""

from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from algotrade.services.read.screens.runs import last_run_rows
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.backends.runs.run_selection import StaleSnapshotError
from algotrade.storage.tables.interfaces import Backend
from tests.helpers.stored_frames import T0, stamped

D1 = date(2026, 10, 1)
TABLE = "results/rule_screen"
AT = T0 + timedelta(minutes=30)
KEY = ["user_id", "config_id", "instrument_id"]
SEEN = ["user_id", "config_id", "instrument_id", "run_id", "decision"]


@pytest.fixture(params=["memory", "local"])
def backend(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Backend]:
    yield MemoryBackend() if request.param == "memory" else LocalBackend(tmp_path / "data")


def rows(
    run: str, config: str, *ids: str, later: int = 0, user: str = "u1", decision: str = "QUALIFIED"
) -> pd.DataFrame:
    data = [
        {
            "instrument_id": i, "user_id": user, "config_id": config, "config_hash": "h",
            "decision": decision, "rank": n, "reasons": f"{run} {i}",
        }
        for n, i in enumerate(ids, start=1)
    ]  # fmt: skip
    return stamped(data, D1, run, knowledge=T0 + timedelta(hours=later))


def publish(backend: Backend, run: str, *frames: pd.DataFrame, restates: bool = False) -> None:
    backend.tables.write(TABLE, D1, run, pd.concat(frames), restates=restates, pending=True)
    backend.tables.commit_run(run, AT)


def expected(backend: Backend, own_run: str | None = None) -> pd.DataFrame:
    """What every reader took until now: the merged partition, each group's newest run."""
    merged = backend.tables.read(TABLE, D1, own_run=own_run)
    assert merged is not None
    kept = [last_run_rows(g)[1] for _, g in merged.groupby(["user_id", "config_id"])]
    return pd.concat(kept)


def same(found: pd.DataFrame | None, want: pd.DataFrame) -> None:
    assert found is not None
    order = [*KEY, "run_id"]
    pd.testing.assert_frame_equal(
        found.sort_values(order).reset_index(drop=True)[SEEN],
        want.sort_values(order).reset_index(drop=True)[SEEN],
    )


def test_one_run_per_group_is_read_as_it_was_merged(backend: Backend) -> None:
    publish(backend, "r1", rows("r1", "a", "EQ:A", "EQ:B"))
    publish(backend, "r2", rows("r2", "b", "EQ:A", later=1))
    same(backend.tables.read_latest_runs(TABLE, D1), expected(backend))


def test_each_older_run_of_a_group_is_left_out(backend: Backend) -> None:
    for n in range(1, 5):
        publish(backend, f"r{n}", rows(f"r{n}", "a", "EQ:A", "EQ:B", later=n))
    found = backend.tables.read_latest_runs(TABLE, D1)
    assert found is not None and set(found["run_id"]) == {"r4"}
    same(found, expected(backend))


def test_a_newer_run_with_fewer_instruments_hides_the_older_runs_others(backend: Backend) -> None:
    publish(backend, "r1", rows("r1", "a", "EQ:A", "EQ:B", "EQ:C"))
    publish(backend, "r2", rows("r2", "a", "EQ:A", later=1))
    found = backend.tables.read_latest_runs(TABLE, D1)
    assert found is not None and list(found["instrument_id"]) == ["EQ:A"]
    same(found, expected(backend))
    only_b = backend.tables.read_latest_runs(TABLE, D1, instruments=["EQ:B"])
    assert only_b is not None and only_b.empty  # the newest run dropped it: never the older one's


def test_interleaved_groups_each_take_their_own_newest_run(backend: Backend) -> None:
    publish(backend, "r1", rows("r1", "a", "EQ:A"))
    publish(backend, "r2", rows("r2", "b", "EQ:A", later=1))
    publish(backend, "r3", rows("r3", "a", "EQ:B", later=2))
    publish(backend, "r4", rows("r4", "b", "EQ:B", later=3, user="u2"))
    found = backend.tables.read_latest_runs(TABLE, D1)
    assert found is not None and sorted(found["run_id"]) == ["r2", "r3", "r4"]
    same(found, expected(backend))


def test_a_knowledge_ts_tie_goes_to_the_later_run_id(backend: Backend) -> None:
    publish(backend, "r2", rows("r2", "a", "EQ:A"))
    publish(backend, "r1", rows("r1", "a", "EQ:A"))
    found = backend.tables.read_latest_runs(TABLE, D1)
    assert found is not None and set(found["run_id"]) == {"r2"}
    same(found, expected(backend))


def test_a_pending_own_run_is_seen_only_by_its_own_reader(backend: Backend) -> None:
    publish(backend, "r1", rows("r1", "a", "EQ:A"))
    backend.tables.write(TABLE, D1, "r2", rows("r2", "a", "EQ:B", later=1), pending=True)
    plain = backend.tables.read_latest_runs(TABLE, D1)
    assert plain is not None and set(plain["run_id"]) == {"r1"}
    own = backend.tables.read_latest_runs(TABLE, D1, own_run="r2")
    assert own is not None and set(own["run_id"]) == {"r2"}
    same(own, expected(backend, own_run="r2"))


def test_a_restating_run_ends_the_merge_it_starts(backend: Backend) -> None:
    publish(backend, "r1", rows("r1", "a", "EQ:A"), rows("r1", "b", "EQ:A"))
    publish(backend, "r2", rows("r2", "a", "EQ:A", "EQ:B", later=1), restates=True)
    found = backend.tables.read_latest_runs(TABLE, D1)
    assert found is not None and set(found["run_id"]) == {"r2"}  # b: before the restatement
    same(found, expected(backend))


def test_a_file_holding_two_groups_gives_each_its_newest_rows(backend: Backend) -> None:
    publish(backend, "r1", rows("r1", "a", "EQ:A"), rows("r1", "b", "EQ:A", "EQ:B"))
    publish(backend, "r2", rows("r2", "a", "EQ:C", later=1))
    found = backend.tables.read_latest_runs(TABLE, D1)
    assert found is not None
    assert sorted(zip(found["config_id"], found["run_id"], strict=True)) == [
        ("a", "r2"), ("b", "r1"), ("b", "r1"),
    ]  # fmt: skip
    same(found, expected(backend))
    same(
        backend.tables.read_latest_runs(TABLE, D1, instruments=["EQ:A"]),
        expected(backend).query("instrument_id == 'EQ:A'"),
    )


def test_columns_keep_the_group_and_the_stamps(backend: Backend) -> None:
    publish(backend, "r1", rows("r1", "a", "EQ:A"))
    found = backend.tables.read_latest_runs(TABLE, D1, columns=["decision"])
    assert found is not None
    assert {"decision", "user_id", "config_id", "instrument_id"} <= set(found.columns)
    assert {"session_date", "knowledge_ts", "source", "run_id"} <= set(found.columns)
    assert "reasons" not in found.columns and "rank" not in found.columns


def test_instruments_matching_nothing_is_an_empty_frame_not_none(backend: Backend) -> None:
    publish(backend, "r1", rows("r1", "a", "EQ:A"))
    found = backend.tables.read_latest_runs(TABLE, D1, instruments=["EQ:ZZ"])
    assert found is not None and found.empty and "instrument_id" in found.columns
    none = backend.tables.read_latest_runs(TABLE, D1, instruments=[])
    assert none is not None and none.empty


def test_a_partition_without_runs_is_none(backend: Backend) -> None:
    publish(backend, "r1", rows("r1", "a", "EQ:A"))
    assert backend.tables.read_latest_runs(TABLE, date(2026, 10, 2)) is None


def test_a_table_whose_runs_are_not_whole_per_group_is_refused(backend: Backend) -> None:
    with pytest.raises(ValueError, match="whole result"):
        backend.tables.read_latest_runs("rollups/instrument/a@v1", D1)
    with pytest.raises(ValueError, match="whole result"):
        backend.tables.read_latest_runs("no/such/table", D1)


def test_a_replaced_pinned_version_is_stale_not_wrong(backend: Backend) -> None:
    publish(backend, "r1", rows("r1", "a", "EQ:A"))
    pinned = backend.tables.visible_seq()
    for n in range(2):  # the same run commits twice more: its version at ``pinned`` is discarded
        publish(backend, "r1", rows("r1", "a", f"EQ:{n}", later=n))
    with pytest.raises(StaleSnapshotError):
        backend.tables.read_latest_runs(TABLE, D1, upto=pinned)
    fresh = backend.tables.read_latest_runs(TABLE, D1)
    assert fresh is not None and list(fresh["instrument_id"]) == ["EQ:1"]


# ---- the local backend: footers, files, the retry


def _local(tmp_path: Path) -> LocalBackend:
    return LocalBackend(tmp_path / "data")


def _rewrite(backend: LocalBackend, run: str, **options: object) -> None:
    """The run's file written again by pyarrow with ``options`` (row group size, statistics)."""
    directory = backend.tables._dir(TABLE, D1)
    path = next(directory.glob(f"run={run}*.parquet"))
    table = pq.read_table(path)
    pq.write_table(table, path, **options)


def _no_merge(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("the fast path merged the whole partition")

    monkeypatch.setattr("algotrade.storage.backends.local.LocalTables._partition", refuse)


def test_the_fast_path_decodes_only_the_newest_runs_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = _local(tmp_path)
    for n in range(1, 4):
        publish(backend, f"r{n}", rows(f"r{n}", "a", "EQ:A", later=n))
    publish(backend, "o1", rows("o1", "b", "EQ:A"))
    reads: list[str] = []
    real = pq.ParquetFile.read

    def counted(self: pq.ParquetFile, *args: object, **kwargs: object) -> object:
        reads.append(self.metadata.num_rows)
        return real(self, *args, **kwargs)

    monkeypatch.setattr(pq.ParquetFile, "read", counted)
    _no_merge(monkeypatch)
    found = backend.tables.read_latest_runs(TABLE, D1)
    assert found is not None and sorted(found["run_id"]) == ["o1", "r3"]
    assert len(reads) == 2  # not 4


def test_a_file_without_statistics_falls_back_to_the_merge(tmp_path: Path) -> None:
    backend = _local(tmp_path)
    publish(backend, "r1", rows("r1", "a", "EQ:A", "EQ:B"))
    publish(backend, "r2", rows("r2", "a", "EQ:A", later=1))
    publish(backend, "r3", rows("r3", "b", "EQ:A", later=2))
    _rewrite(backend, "r2", write_statistics=False)
    found = backend.tables.read_latest_runs(TABLE, D1)
    assert found is not None and sorted(found["run_id"]) == ["r2", "r3"]
    same(found, expected(backend))


def test_row_groups_of_different_groups_fall_back_to_the_merge(tmp_path: Path) -> None:
    backend = _local(tmp_path)
    publish(backend, "r1", rows("r1", "a", "EQ:A"), rows("r1", "b", "EQ:A"))
    publish(backend, "r2", rows("r2", "a", "EQ:B", later=1))
    _rewrite(backend, "r1", row_group_size=1)  # each row group names one value: two groups
    found = backend.tables.read_latest_runs(TABLE, D1)
    assert found is not None
    same(found, expected(backend))
    assert sorted(zip(found["config_id"], found["run_id"], strict=True)) == [
        ("a", "r2"), ("b", "r1"),
    ]  # fmt: skip


def test_one_value_per_row_group_in_one_file_still_takes_the_fast_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = _local(tmp_path)
    publish(backend, "r1", rows("r1", "a", "EQ:A", "EQ:B", "EQ:C"))
    _rewrite(backend, "r1", row_group_size=1)
    _no_merge(monkeypatch)
    found = backend.tables.read_latest_runs(TABLE, D1)
    assert found is not None and len(found) == 3


def test_a_file_a_commit_removed_is_stale_never_an_error(tmp_path: Path) -> None:
    backend = _local(tmp_path)
    publish(backend, "r1", rows("r1", "a", "EQ:A"))
    directory = backend.tables._dir(TABLE, D1)
    next(directory.glob("run=r1*.parquet")).unlink()
    with pytest.raises(StaleSnapshotError):
        backend.tables.read_latest_runs(TABLE, D1, upto=backend.tables.visible_seq())


def test_a_commit_during_the_read_makes_it_start_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = _local(tmp_path)
    publish(backend, "r1", rows("r1", "a", "EQ:A"))
    stale = backend.tables.visible_seq()
    for n in range(2):  # r1's version at ``stale`` is gone
        publish(backend, "r1", rows("r1", "a", f"EQ:{n}", later=n))
    real = backend.tables.commits.published
    calls: list[int] = []

    def published() -> int:
        calls.append(1)
        return stale if len(calls) == 1 else real()

    monkeypatch.setattr(backend.tables.commits, "published", published)
    found = backend.tables.read_latest_runs(TABLE, D1)
    assert len(calls) == 2  # the first sequence was stale: read again at a fresh one
    assert found is not None and list(found["instrument_id"]) == ["EQ:1"]
