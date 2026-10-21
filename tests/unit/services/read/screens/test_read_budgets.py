"""The per-read memory budget of the screen rows (``docs/perf/api-memory.md``, guard 3): a session
holds many reruns of many configs, and a read decodes only each config's newest run. Peak Arrow
allocation is measured through a proxy of the default pool installed for the read, so what ran
earlier in the process does not count. The value readers are budgeted the same way: a run's values
come from that run's own file and for its own picks, never from the session's every run (the
union of every run's picks filtered all of them), and a run that is not its config's newest reads
its own rows."""

import gc
import weakref
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pytest

from algotrade.data import StoreReader
from algotrade.services.read.context import MAX_CACHE_BYTES, ReadContext, partition, weigh
from algotrade.services.read.screens import results, runs
from algotrade.services.read.screens.results import VALUE_COLUMNS, _read_values, run_withheld
from algotrade.services.read.screens.runs import (
    DETAIL_COLUMNS,
    ROW_COLUMNS,
    RULE_SCREEN,
    RunRows,
    RunSummaries,
    ScreenerRun,
    load_latest_runs,
    run_rows,
    run_summaries,
)
from algotrade.storage.backends.arrow import to_arrow
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.tables.schemas import result_table
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped, write_reference
from tests.unit.services.read.screens.conftest import D1, T, context

VR, VRUNS, VINST, PICKED = 20, 5, 200, 3  # the values-read tests: configs, runs, instruments, picks
RULE_SCREEN_VALUES = result_table("rule_screen_values")
CONFIGS, RUNS, INSTRUMENTS = 20, 10, 400


def _frame(config: int, run: int) -> pd.DataFrame:
    rows: list[dict[str, object]] = [
        {"instrument_id": f"EQ:S{i}", "user_id": "site", "config_id": f"c{config}",
         "config_version": 1, "config_hash": "h", "decision": "QUALIFIED", "score": 1.0,
         "rank": i, "tie_break": None, "flags": "", "reasons": f"c{config} r{run} " + "x" * 200,
         "failed": "", "near_missed": "", "missing": ""}
        for i in range(INSTRUMENTS)
    ]  # fmt: skip
    return stamped(rows, D1, f"c{config}-r{run}", T + timedelta(hours=run))


@pytest.fixture
def store(tmp_path: Path) -> tuple[LocalBackend, int]:
    """A session of 10 runs of each of 20 configs; -> it and the Arrow bytes of the newest runs."""
    backend = LocalBackend(tmp_path / "data")
    writer = StoreWriter(backend)
    write_reference(writer, D1, {f"S{i}": f"EQ:S{i}" for i in range(INSTRUMENTS)})
    bar = {"instrument_id": "EQ:S0", "ts": pd.Timestamp(D1, tz="UTC"), "open": 1.0, "high": 1.0,
           "low": 1.0, "close": 1.0, "volume": 1.0}  # fmt: skip
    writer.write_table("bars/1d", D1, "bars", stamped([bar], D1, "bars"))
    newest = 0
    for run in range(RUNS):
        for config in range(CONFIGS):
            frame = _frame(config, run)
            writer.write_result("rule_screen", D1, frame["run_id"].iloc[0], frame)
            if run == RUNS - 1:
                newest += to_arrow("results/rule_screen", frame).nbytes
    return backend, newest


@pytest.fixture
def proxy() -> Iterator[pa.ProxyMemoryPool]:
    before = pa.default_memory_pool()
    pool = pa.proxy_memory_pool(before)
    pa.set_memory_pool(pool)
    try:
        yield pool
    finally:
        pa.set_memory_pool(before)


def test_the_run_summaries_read_stays_within_twice_the_newest_runs_bytes(
    store: tuple[LocalBackend, int], proxy: pa.ProxyMemoryPool
) -> None:
    backend, newest = store
    ctx = context(StoreReader(backend))
    found = run_summaries(ctx)
    assert isinstance(found, RunSummaries) and len(found.by_key) == CONFIGS
    assert all(s.run_id.endswith(f"r{RUNS - 1}") for s in found.by_key.values())
    assert proxy.max_memory() <= 2 * newest


def test_the_summaries_keep_no_frame_after_they_are_built(
    store: tuple[LocalBackend, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    backend, _ = store
    ctx = context(StoreReader(backend))
    seen: list[weakref.ref[pd.DataFrame]] = []

    def watching(*args: Any, **kwargs: Any) -> Any:
        found = partition(*args, **kwargs)
        if isinstance(found, pd.DataFrame):
            seen.append(weakref.ref(found))
        return found

    monkeypatch.setattr(runs, "partition", watching)
    run_summaries(ctx)
    gc.collect()
    assert len(seen) == 1 and seen[0]() is None  # the rows are gone once they are counted
    key = ("run_summaries", ctx.session.date, ctx.reader.own_run, ctx.reader.visible_seq())
    # the guard: about a hundred bytes a screener in the cache, not a frame
    assert 0 < ctx.cache._weights[key] < 100_000
    assert max(ctx.cache._weights.values()) <= MAX_CACHE_BYTES // 2


def test_the_budget_would_catch_the_merge_of_every_run(
    store: tuple[LocalBackend, int], proxy: pa.ProxyMemoryPool
) -> None:
    backend, newest = store
    ctx = context(StoreReader(backend))
    partition(ctx, RULE_SCREEN, ROW_COLUMNS)  # the read before the newest-run rule
    assert proxy.max_memory() > 2 * newest


def _values(config: int, run: int) -> pd.DataFrame:
    rows: list[dict[str, object]] = [
        {"instrument_id": f"EQ:S{i}", "user_id": "site", "config_id": f"c{config}",
         "criterion_id": "k", "field": "feature.f", "mode": "hard", "value_num": 1.0,
         "value_str": "v" * 100, "outcome": "PASS", "distance": None}
        for i in range(INSTRUMENTS)
    ]  # fmt: skip
    return stamped(rows, D1, f"c{config}-r{run}", T + timedelta(hours=run))


def test_the_withheld_fields_of_every_run_decode_one_runs_values_each(
    store: tuple[LocalBackend, int],
) -> None:
    # the values partition holds every rerun of every config (146 million rows on the real
    # store): reading it whole for each run's fields decoded it once per run
    backend, _ = store
    writer = StoreWriter(backend)
    newest = 0
    for run in range(RUNS):
        for config in range(CONFIGS):
            frame = _values(config, run)
            writer.write_result("rule_screen_values", D1, frame["run_id"].iloc[0], frame)
            if run == RUNS - 1:
                newest += to_arrow("results/rule_screen_values", frame).nbytes
    ctx = context(StoreReader(backend), user="trader")  # holds no licence: reads the values
    keys = [("site", f"c{c}") for c in range(CONFIGS)]
    found = [lr.run for lr in load_latest_runs(ctx, keys).values()]
    assert all(run is not None for run in found)
    before = pa.default_memory_pool()
    proxy = pa.proxy_memory_pool(before)
    pa.set_memory_pool(proxy)
    try:
        for run in found:
            assert run is not None
            run_withheld(ctx, run)
    finally:
        pa.set_memory_pool(before)
    # each run decodes its own file once (about 2.7x its bytes with the filter's copy); reading
    # the newest runs of every config per run was 20x
    assert proxy.total_bytes_allocated() <= 4 * newest


def test_the_budget_would_catch_a_values_partition_read_per_run(
    store: tuple[LocalBackend, int],
) -> None:
    # the values partition holds every rerun of every config (146 million rows on the real
    # store): reading it whole for each run's fields decoded it once per run
    backend, _ = store
    writer = StoreWriter(backend)
    newest = 0
    for run in range(RUNS):
        for config in range(CONFIGS):
            frame = _values(config, run)
            writer.write_result("rule_screen_values", D1, frame["run_id"].iloc[0], frame)
            if run == RUNS - 1:
                newest += to_arrow("results/rule_screen_values", frame).nbytes
    ctx = context(StoreReader(backend), user="trader")  # holds no licence: reads the values
    keys = [("site", f"c{c}") for c in range(CONFIGS)]
    found = [lr.run for lr in load_latest_runs(ctx, keys).values()]
    assert all(run is not None for run in found)
    before = pa.default_memory_pool()
    proxy = pa.proxy_memory_pool(before)
    pa.set_memory_pool(proxy)
    try:
        for run in found:
            assert run is not None
            partition(ctx, RULE_SCREEN_VALUES, VALUE_COLUMNS, newest_runs=True)  # P1's per-run read
    finally:
        pa.set_memory_pool(before)
    # each run decodes its own file once (about 2.7x its bytes with the filter's copy); reading
    # the newest runs of every config per run was 20x
    assert proxy.total_bytes_allocated() > 4 * newest


def _values_frame(config: int, run: int, field: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = [
        {"instrument_id": f"EQ:S{i}", "user_id": "site", "config_id": f"c{config}",
         "criterion_id": "k", "field": field, "mode": "hard", "value_num": float(i),
         "value_str": None, "outcome": "PASS", "distance": None}
        for i in range(VINST)
    ]  # fmt: skip
    return stamped(rows, D1, f"c{config}-r{run}", T + timedelta(hours=run))


def _screen_frame(config: int, run: int) -> pd.DataFrame:
    rows: list[dict[str, object]] = [
        {"instrument_id": f"EQ:S{i}", "user_id": "site", "config_id": f"c{config}",
         "config_version": 1, "config_hash": "h", "decision": "QUALIFIED", "score": 1.0,
         "rank": i, "tie_break": None, "flags": "", "reasons": "", "failed": "",
         "near_missed": "", "missing": ""}
        for i in range(VINST)
    ]  # fmt: skip
    return stamped(rows, D1, f"c{config}-r{run}", T + timedelta(hours=run))


@pytest.fixture
def values_store(tmp_path: Path) -> LocalBackend:
    backend = LocalBackend(tmp_path / "data")
    writer = StoreWriter(backend)
    write_reference(writer, D1, {f"S{i}": f"EQ:S{i}" for i in range(VINST)})
    bar = {"instrument_id": "EQ:S0", "ts": pd.Timestamp(D1, tz="UTC"), "open": 1.0, "high": 1.0,
           "low": 1.0, "close": 1.0, "volume": 1.0}  # fmt: skip
    writer.write_table("bars/1d", D1, "bars", stamped([bar], D1, "bars"))
    for run in range(VRUNS):
        for config in range(VR):
            name = f"c{config}-r{run}"
            writer.write_result("rule_screen", D1, name, _screen_frame(config, run))
            # a run's own field: an older run's is not the newest run's
            writer.write_result(
                "rule_screen_values", D1, name, _values_frame(config, run, f"feature.f{run}")
            )
    return backend


def _returned_rows(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """The row counts ``StoreReader.read_run`` and ``read_latest_runs`` hand back."""
    counts: list[int] = []
    for name in ("read_run", "read_latest_runs"):
        real = getattr(StoreReader, name)

        def counting(
            self: StoreReader, *args: object, _real: object = real, **kw: object
        ) -> object:
            found = _real(self, *args, **kw)  # type: ignore[operator]
            counts.append(0 if found is None else len(found))
            return found

        monkeypatch.setattr(StoreReader, name, counting)
    return counts


def _runs_and_wanted(
    backend: LocalBackend, user: str = "trader"
) -> tuple[ReadContext, list[ScreenerRun], dict[str, list[str]]]:
    ctx = context(StoreReader(backend), user=user)
    keys = [("site", f"c{c}") for c in range(VR)]
    found = [lr.run for lr in load_latest_runs(ctx, keys).values() if lr.run is not None]
    assert len(found) == VR
    picks = {  # each run picks its own three: the union of every run's is 60 instruments
        r.run_id: [f"EQ:S{n * PICKED + j}" for j in range(PICKED)] for n, r in enumerate(found)
    }
    return ctx, found, picks


def test_the_values_of_every_run_are_read_for_its_own_picks_only(
    values_store: LocalBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx, runs, wanted = _runs_and_wanted(values_store)
    counts = _returned_rows(monkeypatch)
    found = _read_values(ctx, runs, [i for ids in wanted.values() for i in ids], wanted)
    assert len(found) == VR * PICKED  # one entry per (run, picked instrument)
    assert sum(counts) <= 1.5 * VR * PICKED


def test_the_budget_would_catch_the_union_of_every_runs_picks(
    values_store: LocalBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx, _, wanted = _runs_and_wanted(values_store)
    counts = _returned_rows(monkeypatch)
    union = sorted({i for ids in wanted.values() for i in ids})
    partition(ctx, results.RULE_SCREEN_VALUES, results.VALUE_COLUMNS, union, newest_runs=True)
    assert sum(counts) > 1.5 * VR * PICKED  # every run's rows of the union, read once


def test_the_fields_and_a_sort_key_of_a_run_that_is_not_the_newest_are_its_own(
    values_store: LocalBackend,
) -> None:
    ctx, runs, _ = _runs_and_wanted(values_store, "me")
    newest = runs[0]
    older = replace(newest, run_id="c0-r1")
    assert results._run_fields(ctx, newest) == frozenset({f"feature.f{VRUNS - 1}"})
    assert results._run_fields(ctx, older) == frozenset({"feature.f1"})
    keyed = results._stored_key(ctx, older, "criterion:k")
    assert keyed["EQ:S7"] == 7.0 and len(keyed) == VINST


def test_the_values_of_a_run_that_is_not_the_newest_are_its_own(
    values_store: LocalBackend,
) -> None:
    ctx, runs, _ = _runs_and_wanted(values_store, "me")
    older = replace(runs[0], run_id="c0-r1")
    found = _read_values(ctx, [older], None, {"c0-r1": ["EQ:S4"]})
    assert list(found) == [("c0-r1", "EQ:S4")]
    assert [row["field"] for row in found[("c0-r1", "EQ:S4")]] == ["feature.f1"]


def _held_bytes(ctx: ReadContext, runs: list[ScreenerRun]) -> int:
    """What the asked runs' own rows weigh as frames (``RunRows.weight_bytes``)."""
    held = RunRows()
    for run in runs:
        held.get_or_read(run.run_id, lambda run=run: run_rows(ctx, run))
    return held.weight_bytes()


def _arrow_total(work: Callable[[], object]) -> int:
    """The Arrow bytes allocated, in all, while ``work`` runs."""
    before = pa.default_memory_pool()
    proxy = pa.proxy_memory_pool(before)
    pa.set_memory_pool(proxy)
    try:
        work()
        return proxy.total_bytes_allocated()
    finally:
        pa.set_memory_pool(before)


def _runs(ctx: ReadContext) -> list[ScreenerRun]:
    keys = [("site", f"c{c}") for c in range(CONFIGS)]
    runs = [lr.run for lr in load_latest_runs(ctx, keys).values() if lr.run is not None]
    assert len(runs) == CONFIGS
    return runs


def _all_run_rows_at_once(ctx: ReadContext, runs: list[ScreenerRun]) -> None:
    with ThreadPoolExecutor(max_workers=6) as pool:
        for rows in pool.map(lambda run: run_rows(ctx, run), runs):
            assert len(rows) == INSTRUMENTS


def _split_the_sessions_newest_rows(ctx: ReadContext) -> None:
    """What ``run_rows`` did: every config's newest run, every column, sorted, split per run."""
    stored = partition(ctx, RULE_SCREEN, (*DETAIL_COLUMNS, "config_version"), newest_runs=True)
    assert isinstance(stored, pd.DataFrame)
    ranked = stored.sort_values(["rank", "instrument_id"], kind="stable")
    for _, rows in ranked.groupby(["user_id", "config_id", "run_id"], sort=False):
        rows.reset_index(drop=True)


# A run's own file is decoded (its columns), filtered to the run and conformed: about 3.4x the
# frame it leaves (measured); the session-wide split decoded every column, about 9.6x.
ARROW_BUDGET = 5


def test_run_rows_of_every_run_at_once_read_the_runs_own_rows_only(
    store: tuple[LocalBackend, int],
) -> None:
    backend, _ = store
    runs = _runs(context(StoreReader(backend)))
    held = _held_bytes(context(StoreReader(backend)), runs)
    used = _arrow_total(lambda: _all_run_rows_at_once(context(StoreReader(backend)), runs))
    assert used <= ARROW_BUDGET * held


def test_the_budget_would_catch_cutting_the_runs_out_of_the_sessions_newest_rows(
    store: tuple[LocalBackend, int],
) -> None:
    backend, _ = store
    runs = _runs(context(StoreReader(backend)))
    held = _held_bytes(context(StoreReader(backend)), runs)
    used = _arrow_total(lambda: _split_the_sessions_newest_rows(context(StoreReader(backend))))
    assert used > ARROW_BUDGET * held


def test_the_cache_holds_exactly_what_the_run_rows_container_weighs(
    store: tuple[LocalBackend, int],
) -> None:
    ctx = context(StoreReader(store[0]))
    runs = _runs(ctx)
    run_rows(ctx, runs[0])
    run_rows(ctx, runs[1])
    key = ("run_rows", ctx.session.date, ctx.reader.own_run, ctx.reader.visible_seq())
    held: RunRows = ctx.cache.get(key)
    assert held.weight_bytes() > 0 and ctx.cache._weights[key] == held.weight_bytes()
    assert held.weight_bytes() >= 2 * weigh(run_rows(ctx, runs[0])) * 0.9  # both runs counted


def test_threads_adding_runs_together_leave_the_full_weight_in_the_cache(
    store: tuple[LocalBackend, int],
) -> None:
    ctx = context(StoreReader(store[0]))
    runs = _runs(ctx)
    _all_run_rows_at_once(ctx, runs)
    key = ("run_rows", ctx.session.date, ctx.reader.own_run, ctx.reader.visible_seq())
    assert ctx.cache._weights[key] == ctx.cache.get(key).weight_bytes()
