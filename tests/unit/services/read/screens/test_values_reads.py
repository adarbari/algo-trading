"""What the screen value readers decode (``docs/perf/api-memory.md``): a run's values are read from
that run's own file, for the instruments asked for, never from the session's every run. A session
holds every rerun of every config (146 million value rows on the real store)."""

from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pandas as pd
import pytest

from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext, partition
from algotrade.services.read.screens import results
from algotrade.services.read.screens.results import _read_values
from algotrade.services.read.screens.runs import ScreenerRun, load_latest_runs
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped, write_reference
from tests.unit.services.read.screens.conftest import D1, T, context

CONFIGS, RUNS, INSTRUMENTS, PICKED = 20, 5, 200, 3


def _frame(config: int, run: int, field: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = [
        {"instrument_id": f"EQ:S{i}", "user_id": "site", "config_id": f"c{config}",
         "criterion_id": "k", "field": field, "mode": "hard", "value_num": float(i),
         "value_str": None, "outcome": "PASS", "distance": None}
        for i in range(INSTRUMENTS)
    ]  # fmt: skip
    return stamped(rows, D1, f"c{config}-r{run}", T + timedelta(hours=run))


def _screen(config: int, run: int) -> pd.DataFrame:
    rows: list[dict[str, object]] = [
        {"instrument_id": f"EQ:S{i}", "user_id": "site", "config_id": f"c{config}",
         "config_version": 1, "config_hash": "h", "decision": "QUALIFIED", "score": 1.0,
         "rank": i, "tie_break": None, "flags": "", "reasons": "", "failed": "",
         "near_missed": "", "missing": ""}
        for i in range(INSTRUMENTS)
    ]  # fmt: skip
    return stamped(rows, D1, f"c{config}-r{run}", T + timedelta(hours=run))


@pytest.fixture
def store(tmp_path: Path) -> LocalBackend:
    backend = LocalBackend(tmp_path / "data")
    writer = StoreWriter(backend)
    write_reference(writer, D1, {f"S{i}": f"EQ:S{i}" for i in range(INSTRUMENTS)})
    bar = {"instrument_id": "EQ:S0", "ts": pd.Timestamp(D1, tz="UTC"), "open": 1.0, "high": 1.0,
           "low": 1.0, "close": 1.0, "volume": 1.0}  # fmt: skip
    writer.write_table("bars/1d", D1, "bars", stamped([bar], D1, "bars"))
    for run in range(RUNS):
        for config in range(CONFIGS):
            name = f"c{config}-r{run}"
            writer.write_result("rule_screen", D1, name, _screen(config, run))
            # a run's own field: an older run's is not the newest run's
            writer.write_result(
                "rule_screen_values", D1, name, _frame(config, run, f"feature.f{run}")
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
    keys = [("site", f"c{c}") for c in range(CONFIGS)]
    found = [lr.run for lr in load_latest_runs(ctx, keys).values() if lr.run is not None]
    assert len(found) == CONFIGS
    picks = {  # each run picks its own three: the union of every run's is 60 instruments
        r.run_id: [f"EQ:S{n * PICKED + j}" for j in range(PICKED)] for n, r in enumerate(found)
    }
    return ctx, found, picks


def test_the_values_of_every_run_are_read_for_its_own_picks_only(
    store: LocalBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx, runs, wanted = _runs_and_wanted(store)
    counts = _returned_rows(monkeypatch)
    found = _read_values(ctx, runs, [i for ids in wanted.values() for i in ids], wanted)
    assert len(found) == CONFIGS * PICKED  # one entry per (run, picked instrument)
    assert sum(counts) <= 1.5 * CONFIGS * PICKED


def test_the_budget_would_catch_the_union_of_every_runs_picks(
    store: LocalBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx, _, wanted = _runs_and_wanted(store)
    counts = _returned_rows(monkeypatch)
    union = sorted({i for ids in wanted.values() for i in ids})
    partition(ctx, results.RULE_SCREEN_VALUES, results.VALUE_COLUMNS, union, newest_runs=True)
    assert sum(counts) > 1.5 * CONFIGS * PICKED  # every run's rows of the union, read once


def test_the_fields_and_a_sort_key_of_a_run_that_is_not_the_newest_are_its_own(
    store: LocalBackend,
) -> None:
    ctx, runs, _ = _runs_and_wanted(store, "me")
    newest = runs[0]
    older = replace(newest, run_id="c0-r1")
    assert results._run_fields(ctx, newest) == frozenset({f"feature.f{RUNS - 1}"})
    assert results._run_fields(ctx, older) == frozenset({"feature.f1"})
    keyed = results._stored_key(ctx, older, "criterion:k")
    assert keyed["EQ:S7"] == 7.0 and len(keyed) == INSTRUMENTS
