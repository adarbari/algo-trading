"""The local backend's version-file reader: ``_read_file`` decodes exactly what
``pq.read_table`` did (same columns, types, metadata and row order), a whole range read too,
and an empty instrument list still raises (the contract suite covers everything else).

Table listing (``names``) walks directories only and equals the recursive glob it replaced,
on nested table paths and with stray directories.

The ``perf`` tests are the budget of Market.history's read (13,500 one-row partitions, two
columns) and of the table listing (50,000 partitions), serial, cold, on an idle machine
(``make perf``): the first ceiling is the time measured when it landed (target under 5 s,
docs/roadmap.md); the listing's is 0.2 s."""

import os
import shutil
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from algotrade.storage.backends import local
from algotrade.storage.backends.local import LocalBackend, _read_file
from algotrade.storage.runs import RunRecord, RunStatus, start_run
from tests.helpers.stored_frames import T0, stamped

D1 = date(2026, 10, 1)

TABLE = "rollups/market/demo@v1"
START = date(1971, 1, 1)
BUDGET_S = 15.0  # the perf test's ceiling: the measured serial read (see the PR), not the target


def _days(n: int) -> list[date]:
    return [START + timedelta(days=i) for i in range(n)]


def _write(root: Path, n: int) -> LocalBackend:
    backend = LocalBackend(root)
    for i, day in enumerate(_days(n)):
        rows = [
            {"instrument_id": f"EQ:{s}", "a": float(i), "b": i * 2, "c": f"{s}{i}"} for s in "XYZ"
        ]
        backend.tables.write(TABLE, day, "r1", stamped(rows, day, "r1"))
        if i % 7 == 0:  # a later run restating some partitions: two versions to select from
            later = T0 + timedelta(hours=1)
            backend.tables.write(TABLE, day, "r2", stamped(rows[:1], day, "r2", later))
    return backend


def _read_table(path: Path, instruments: Any, columns: Any) -> pa.Table:
    """The reader before this change (``read_table`` with a filter), for comparison."""
    filters = None if instruments is None else [("instrument_id", "in", list(instruments))]
    if columns is None:
        return pq.read_table(path, filters=filters)
    keep = local.keep_columns(columns)
    present = [c for c in pq.read_schema(path).names if c in keep]
    return pq.read_table(path, filters=filters, columns=present)


def _first_file(store: Path) -> Path:
    return next((store / "tables" / TABLE / f"date={START.isoformat()}").glob("run=r1*.parquet"))


@pytest.fixture(scope="module")
def store(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("local") / "data"
    _write(root, 30)
    return root


@pytest.mark.parametrize(
    ("instruments", "columns"),
    [(None, None), (["EQ:Y"], None), (None, ["a"]), (["EQ:Z", "EQ:X"], ["b"]), (["EQ:Q"], None)],
)
def test_read_file_decodes_what_read_table_did(
    store: Path, instruments: list[str] | None, columns: list[str] | None
) -> None:
    path = _first_file(store)
    expected = _read_table(path, instruments, columns)
    assert _read_file(path, instruments, columns).equals(expected, check_metadata=True)


def test_no_instruments_select_no_rows(store: Path) -> None:
    """An empty "in" list once raised ``ArrowTypeError`` (a null-typed set against a
    ``large_string`` id column) and failed every ETF event study in the API."""
    path = _first_file(store)
    out = _read_file(path, [], None)
    assert out.num_rows == 0
    assert out.schema.equals(_read_file(path, None, None).schema)


@pytest.mark.parametrize("id_type", [pa.string(), pa.large_string()])
@pytest.mark.parametrize(("instruments", "kept"), [([], []), (["EQ:B"], ["EQ:B"])])
def test_the_value_set_takes_the_id_column_type(
    tmp_path: Path, id_type: pa.DataType, instruments: list[str], kept: list[str]
) -> None:
    """Files written before the schemas were typed hold ``string`` ids, newer ones
    ``large_string``: an instrument filter (empty included) reads both."""
    path = tmp_path / "v.parquet"
    ids = pa.array(["EQ:A", "EQ:B"], type=id_type)
    pq.write_table(pa.table({"instrument_id": ids, "value": [1.0, 2.0]}), path)
    out = _read_file(path, instruments, None)
    assert out.column("instrument_id").to_pylist() == kept
    assert out.schema.field("instrument_id").type == id_type


@pytest.mark.parametrize(
    ("instruments", "columns", "as_of"),
    [(None, None, None), (["EQ:X", "EQ:Z"], ["a"], None), (None, ["b"], T0)],
)
def test_a_range_read_equals_the_read_table_one(
    store: Path,
    monkeypatch: pytest.MonkeyPatch,
    instruments: list[str] | None,
    columns: list[str] | None,
    as_of: Any,
) -> None:
    args = (TABLE, START, _days(30)[-1], as_of, instruments, None, columns)
    out = LocalBackend(store).tables.read_range(*args)
    monkeypatch.setattr(local, "_read_file", _read_table)
    expected = LocalBackend(store).tables.read_range(*args)
    assert out is not None and expected is not None and len(out) > 30
    pd.testing.assert_frame_equal(out, expected, check_exact=True)


@pytest.mark.perf
def test_a_13500_partition_two_column_read_is_within_budget(tmp_path: Path) -> None:
    n = 13_500
    root = tmp_path / "data"
    _write(root, 1)  # one partition, copied: writing 13,500 through the index takes ~40 s
    base = root / "tables" / TABLE
    first = base / f"date={START.isoformat()}"
    for day in _days(n)[1:]:
        shutil.copytree(first, base / f"date={day.isoformat()}")
    start = time.perf_counter()
    out = LocalBackend(root).tables.read_range(TABLE, START, _days(n)[-1], columns=["a", "b"])
    elapsed = time.perf_counter() - start
    assert out is not None and len(out) == n  # the restating r2 (one row) is the latest
    assert elapsed < BUDGET_S, f"{elapsed:.2f} s for {n} partitions (budget {BUDGET_S} s)"


def _index_files(tables: Path, layout: dict[str, int]) -> None:
    """Indexed partitions (a bare ``_runs.json``: all the listing looks at) per table path."""
    for table, n in layout.items():
        for day in _days(n):
            partition = tables / table / f"date={day.isoformat()}"
            partition.mkdir(parents=True)
            (partition / local.INDEX).write_text("{}")


def test_table_names_equal_the_recursive_glob_on_nested_tables_and_stray_directories(
    tmp_path: Path,
) -> None:
    tables = tmp_path / "data" / "tables"
    _index_files(
        tables,
        {"bars/1d": 3, "rollups/market/regime@v2": 2, "macro/series": 1, "reference": 4},
    )
    (tables / "stray" / "empty").mkdir(parents=True)  # a directory with no partition
    (tables / "stray" / "notes.txt").write_text("x")
    (tables / "unindexed" / "date=2020-01-01").mkdir(parents=True)  # a day with no index
    (tables / "bars" / "1d" / f"date={START.isoformat()}" / "file.parquet").write_text("x")
    (tables / "_txn" / "commits").mkdir(parents=True)
    (tables / "_txn" / "commits" / "r1.json").write_text("{}")
    old = sorted(
        {
            p.parent.parent.relative_to(tables).as_posix()
            for p in tables.glob(f"**/date=*/{local.INDEX}")
        }
    )
    names = LocalBackend(tmp_path / "data").tables.names()
    assert names == old == ["bars/1d", "macro/series", "reference", "rollups/market/regime@v2"]


def test_table_names_of_an_empty_store_are_empty(tmp_path: Path) -> None:
    assert LocalBackend(tmp_path / "data").tables.names() == []


@pytest.mark.perf
def test_listing_tables_of_50000_partitions_is_within_budget(tmp_path: Path) -> None:
    tables = tmp_path / "data" / "tables"
    _index_files(
        tables,
        {"bars/1d": 20_000, "rollups/market/regime@v2": 20_000, "macro/series": 10_000},
    )
    backend = LocalBackend(tmp_path / "data")
    start = time.perf_counter()
    names = backend.tables.names()
    elapsed = time.perf_counter() - start
    assert names == ["bars/1d", "macro/series", "rollups/market/regime@v2"]
    assert elapsed < 0.2, f"{elapsed:.3f} s for 50,000 partitions (budget 0.2 s)"


def test_find_opens_only_the_job_s_files_and_parses_a_file_once_per_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every record of a store was parsed on every ``find`` (6 400 files, 0.9 s a call, 26
    calls for the edges page): only the job's own ``new_run_id`` files (and files in another
    id form) are opened, and a file is parsed again only once it changed."""
    runs = LocalBackend(tmp_path).runs
    for n, job in enumerate(["job", "other", "other", "other"]):
        runs.save(start_run(job, D1, T0 + timedelta(n)))
    runs.save(RunRecord("job-screen-0123456789abcdef", "job:screen", D1, T0))
    parsed: list[str] = []
    original = RunRecord.from_json

    def spy(text: str) -> RunRecord:
        record = original(text)
        parsed.append(record.job)
        return record

    monkeypatch.setattr(local.RunRecord, "from_json", staticmethod(spy))
    assert [r.job for r in runs.find("job")] == ["job"]
    assert sorted(parsed) == ["job", "job:screen"]  # never another job's records
    runs.find("job")
    assert len(parsed) == 2  # unchanged files: nothing parsed again
    record = runs.find("job")[0]
    time.sleep(0.01)
    runs.save(record.finish(T0 + timedelta(1)))
    assert runs.find("job")[0].status is RunStatus.COMPLETE and len(parsed) == 3


def test_the_parsed_run_cache_evicts_past_its_byte_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``LocalRuns._parsed`` grew with the runs folder (50 MB, 6 400 files, nightly more)."""
    runs = LocalBackend(tmp_path).runs
    for n in range(6):
        runs.save(start_run("job", D1, T0 + timedelta(n)))
    size = max(p.stat().st_size for p in (tmp_path / "runs").glob("*.json"))
    monkeypatch.setattr(local, "MAX_PARSED_BYTES", 2 * size)
    assert len(runs.find("job")) == 6
    assert 0 < len(runs._parsed) <= 2 and runs._parsed_bytes <= 2 * size


def test_find_lists_the_runs_directory_once_per_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The edges page called ``find`` 26 times, each listing ~10 000 files (0.4 s of the 0.6 s):
    the listing is kept until a save changes the directory, and a run saved after a ``find`` is
    still found by the next (same answer as an uncached listing)."""
    runs = LocalBackend(tmp_path).runs
    runs.save(start_run("job", D1, T0))
    listed: list[str] = []
    original = local.run_session

    def spy(stem: str) -> date | None:
        listed.append(stem)
        return original(stem)

    monkeypatch.setattr(local, "run_session", spy)
    first = runs.find("job")
    assert runs.find("job") == first and runs.find("job", D1) == first
    assert len(listed) == 1  # one listing (one file) for three finds
    time.sleep(0.01)
    runs.save(start_run("job", D1, T0 + timedelta(1)))
    assert len(runs.find("job")) == 2 and len(listed) == 3  # a save invalidates it


def test_a_short_range_probes_its_days_and_reads_what_the_listing_reads(
    store: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # a one-session read of a 4,000-partition table listed every directory (75 ms) to find one
    tables = LocalBackend(store).tables
    day = _days(30)[9]
    listed = tables.read_range(TABLE, day, day + timedelta(days=11))
    monkeypatch.setattr(local.LocalTables, "dates", lambda *_a, **_k: pytest.fail("listed"))
    probed = tables.read_range(TABLE, day, day + timedelta(days=11))
    assert listed is not None and probed is not None and len(probed) > 12
    pd.testing.assert_frame_equal(probed, listed, check_exact=True)
    assert tables.read_range(TABLE, date(1990, 1, 1), date(1990, 1, 5)) is None  # no partition


def test_partition_seq_equals_the_sorted_glob_it_replaced(tmp_path: Path) -> None:
    """``partition_seq`` filters directory names by date before touching any path: the same
    dict, in ascending date order, as the glob over every partition directory it replaced, with
    out-of-range days, an unindexed day and stray entries around."""
    backend = _write(tmp_path / "data", 30)
    base = tmp_path / "data" / "tables" / TABLE
    (base / f"date={(START + timedelta(days=40)).isoformat()}").mkdir()  # a day with no index
    (base / "notes.txt").write_text("x")
    start, end = START + timedelta(days=5), START + timedelta(days=20)
    published = backend.tables.commits.published()
    old = {}
    for day in sorted(base.glob("date=*")):
        when = date.fromisoformat(day.name.removeprefix("date="))
        if start <= when <= end and (day / local.INDEX).exists():
            old[when] = local.max_seq(local.read_index(day), published)
    found = backend.tables.partition_seq(TABLE, start, end)
    assert found == old and list(found) == sorted(found) and len(found) == 16


def _one() -> list[dict[str, Any]]:
    return [{"instrument_id": "EQ:X", "a": 1.0, "b": 1, "c": "x"}]


def test_listing_the_live_dates_is_kept_until_the_store_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One filesystem listing per (table, published sequence, epoch): a second ``dates`` and
    any number of ``has_partition`` probes do no directory scan, and a commit re-lists."""
    backend = LocalBackend(tmp_path / "data")
    for day in _days(5):
        backend.tables.write(TABLE, day, "r", stamped(_one(), day, "r"), pending=True)
    backend.tables.commit_run("r", T0 + timedelta(hours=1))
    scans = {"n": 0}
    real = backend.tables._list_dates

    def counting_list(table: str) -> Any:
        scans["n"] += 1
        return real(table)

    monkeypatch.setattr(backend.tables, "_list_dates", counting_list)
    first = backend.tables.dates(TABLE)
    assert backend.tables.dates(TABLE) == first and scans["n"] == 1
    assert all(backend.tables.has_partition(TABLE, d) for d in first) and scans["n"] == 1
    late = START + timedelta(days=9)
    backend.tables.write(TABLE, late, "r2", stamped(_one(), late, "r2"), pending=True)
    backend.tables.commit_run("r2", T0 + timedelta(hours=2))
    assert backend.tables.dates(TABLE) == [*first, late] and scans["n"] == 2


def test_a_pending_partition_is_merged_over_the_kept_listing(tmp_path: Path) -> None:
    backend = LocalBackend(tmp_path / "data")
    backend.tables.write(TABLE, START, "r", stamped(_one(), START, "r"), pending=True)
    backend.tables.commit_run("r", T0 + timedelta(hours=1))
    assert backend.tables.dates(TABLE) == [START]  # kept now
    day = START + timedelta(days=1)
    backend.tables.write(TABLE, day, "open", stamped(_one(), day, "open"), pending=True)
    assert backend.tables.dates(TABLE, "open") == [START, day]
    assert backend.tables.dates(TABLE) == [START]  # another reader: not there
    backend.tables.abort_run("open")
    assert backend.tables.dates(TABLE, "open") == [START]


def test_has_partition_is_one_stat_not_a_walk_of_the_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cost of asking whether one day exists is independent of the partitions the table
    holds (the uncached SessionDate did 340,846 stats: one per partition per table)."""
    backend = LocalBackend(tmp_path / "data")
    tables = [f"rollups/market/t{i}@v1" for i in range(4)]
    for table in tables:
        for day in _days(30):
            backend.tables.write(table, day, "d", stamped(_one(), day, "d"))
    stats = {"n": 0}
    real = os.stat

    def counting(path: Any, *args: Any, **kwargs: Any) -> Any:
        stats["n"] += 1
        return real(path, *args, **kwargs)

    monkeypatch.setattr(os, "stat", counting)
    found = [backend.tables.has_partition(t, START) for t in tables]
    assert found == [True] * 4
    assert stats["n"] <= 4 * 3  # a few per table (path checks), never 30 per table


def test_another_process_sees_every_change_on_its_next_call(tmp_path: Path) -> None:
    """The API (reader) and ingestion (writer) are two ``LocalBackend``s on one root: the kept
    listing is keyed on what is on disk (sequence, epoch), never on the process."""
    root = tmp_path / "data"
    reader, writer = LocalBackend(root), LocalBackend(root)
    d2, d3 = START + timedelta(days=1), START + timedelta(days=2)

    def seen() -> list[date]:
        found = reader.tables.dates(TABLE)
        assert [reader.tables.has_partition(TABLE, d) for d in (START, d2, d3)] == [
            d in found for d in (START, d2, d3)
        ]
        return found

    assert seen() == []
    writer.tables.write(TABLE, START, "r", stamped(_one(), START, "r"), pending=True)
    writer.tables.commit_run("r", T0 + timedelta(hours=1))
    assert seen() == [START]  # a commit
    writer.tables.write(TABLE, d2, "direct", stamped(_one(), d2, "direct"))
    assert seen() == [START, d2]  # a direct write
    writer.tables.write(TABLE, d3, "r2", stamped(_one(), d3, "r2"), pending=True)
    writer.tables.commit_run("r2", T0 + timedelta(hours=2))
    assert seen() == [START, d2, d3]
    other = "rollups/market/other@v1"
    writer.tables.write(other, START, "r3", stamped(_one(), START, "r3"))
    assert reader.tables.dates(other) == [START]
    assert writer.tables.drop(other) == 1  # a drop
    assert reader.tables.dates(other) == [] and not reader.tables.has_partition(other, START)
    live = "live/option_quotes"
    for day in (START, d2):
        row = {
            "instrument_id": f"OPT:{day}", "underlying_id": "EQ:A", "expiry": day,
            "ts": pd.Timestamp(day, tz="UTC"), "right": "C", "strike": 100.0, "bid": 1.0,
        }  # fmt: skip
        writer.tables.write(live, day, "q", stamped([row], day, "q"), pending=True)
    writer.tables.commit_run("q", T0 + timedelta(hours=3))
    assert reader.tables.dates(live) == [START, d2]
    assert writer.tables.purge_before(live, d2) == 1  # a purge
    assert reader.tables.dates(live) == [d2] and not reader.tables.has_partition(live, START)
