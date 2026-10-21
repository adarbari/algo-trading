"""The per-read memory budget of the screen rows (``docs/perf/api-memory.md``, guard 3): a session
holds many reruns of many configs, and a read decodes only each config's newest run. Peak Arrow
allocation is measured through a proxy of the default pool installed for the read, so what ran
earlier in the process does not count."""

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pytest

from algotrade.data import StoreReader
from algotrade.services.read.context import partition
from algotrade.services.read.screens.results import run_withheld
from algotrade.services.read.screens.runs import (
    ROW_COLUMNS,
    RULE_SCREEN,
    load_latest_runs,
    screen_rows,
)
from algotrade.services.read.values import Unknown
from algotrade.storage.backends.arrow import to_arrow
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped, write_reference
from tests.unit.services.read.screens.conftest import D1, T, context

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


def test_the_screen_rows_read_stays_within_twice_the_newest_runs_bytes(
    store: tuple[LocalBackend, int], proxy: pa.ProxyMemoryPool
) -> None:
    backend, newest = store
    ctx = context(StoreReader(backend))
    found = screen_rows(ctx)
    assert not isinstance(found, Unknown) and len(found) == CONFIGS * INSTRUMENTS
    assert found["run_id"].str.endswith(f"r{RUNS - 1}").all()
    assert proxy.max_memory() <= 2 * newest


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
