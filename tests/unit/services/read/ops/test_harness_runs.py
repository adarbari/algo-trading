"""The Admin harness runs: every evaluation run of every status for the site and the declared
users, newest first, what each recorded (range, split, exploratory, trial-log figures; a figure
the record lacks is None, never 0), one run by id (never another job's), and its own rows."""

from datetime import date

import pytest

from algotrade.services.read.ops.harness_runs import (
    load_harness_run,
    load_harness_run_rows,
    load_harness_runs,
)
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade.storage.tables.result_writer import ResultWriter
from tests.unit.services.read.evaluation.conftest import (
    END,
    FROZEN,
    START,
    T,
    stores,
    write_run,
)


@pytest.fixture
def backend() -> MemoryBackend:
    return MemoryBackend()


TRIALS = [
    {"variant": "momo", "horizon": 20, "sessions": 12, "excluded_coverage": 2,
     "no_entry_bar": 3, "ranked_share": 0.9},
    {"variant": "base", "horizon": 5, "sessions": 15, "excluded_coverage": 1,
     "no_entry_bar": 7, "ranked_share": 0.6},
]  # fmt: skip


def _record(backend: MemoryBackend, stats: dict[str, object], job: str) -> None:
    ResultWriter(backend).save_run(
        RunRecord("tr", job, END, T).finish(T, complete=True, stats=stats)
    )


def test_every_run_of_any_status_newest_first(backend: MemoryBackend) -> None:
    write_run(backend, "old", FROZEN, 0.5, minutes=0)
    write_run(backend, "mine", date(2026, 3, 1), 0.9, owner="local", minutes=10)
    write_run(backend, "live", FROZEN, 0.5, minutes=20, status=RunStatus.RUNNING)
    runs = load_harness_runs(stores(backend))
    assert [(r.run_id, r.user, r.status) for r in runs] == [
        ("live", "site", "running"), ("mine", "local", "complete"), ("old", "site", "complete"),
    ]  # fmt: skip
    assert [r.run_id for r in load_harness_runs(stores(backend), 1)] == ["live"]
    mine = runs[1]
    assert (mine.edge_id, mine.exploratory, mine.split_from) == ("drift", True, date(2026, 3, 1))
    assert (mine.range_from, mine.range_to, mine.trials) == (START, END, 1)


def test_the_trial_log_figures_and_the_unrecorded(backend: MemoryBackend) -> None:
    stats = {"trials": TRIALS, "unclosed_sessions": {"5": 1, "20": 2}, "trials_counted": 2}
    _record(backend, stats, "edge-eval:drift:site")
    [run] = load_harness_runs(stores(backend))
    assert (run.variants, run.horizons, run.sessions) == (("base", "momo"), (5, 20), 15)
    assert (run.unclosed, run.excluded_coverage, run.no_entry_bar) == (3, 2, 7)
    assert (run.score_coverage, run.trials) == (0.6, 2)
    _record(backend, {}, "edge-eval:drift:local")
    bare = next(r for r in load_harness_runs(stores(backend)) if r.user == "local")
    assert (bare.sessions, bare.unclosed, bare.excluded_coverage, bare.score_coverage) == (
        None, None, None, None,
    )  # fmt: skip
    assert bare.variants == () and bare.knowledge_ts == T


def test_the_lost_input_tables_come_from_the_trial_log(backend: MemoryBackend) -> None:
    trials = [
        {"variant": "momo", "edge_variant": "main", "horizon": 20,
         "lost_sessions": {"rollups/ibkr_iv": 4, "rollups/other": 1}},
        {"variant": "base", "horizon": 5, "lost_sessions": {}},
    ]  # fmt: skip
    _record(backend, {"trials": trials}, "edge-eval:drift:site")
    [run] = load_harness_runs(stores(backend))
    assert [(x.variant, x.horizon, x.table, x.sessions) for x in run.lost_inputs] == [
        ("main/momo", 20, "rollups/ibkr_iv", 4), ("main/momo", 20, "rollups/other", 1),
    ]  # fmt: skip
    _record(backend, {"trials": [{"variant": "v", "horizon": 1}]}, "edge-eval:drift:local")
    bare = next(r for r in load_harness_runs(stores(backend)) if r.user == "local")
    assert bare.lost_inputs == ()  # an older record without the key: none, never invented


def test_one_run_by_id_only_an_evaluation_run(backend: MemoryBackend) -> None:
    write_run(backend, "r1", FROZEN, 0.5)
    ResultWriter(backend).save_run(RunRecord("other", "nightly", END, T))
    ctx = stores(backend)
    found = load_harness_run(ctx, "r1")
    assert found is not None and (found.edge_id, found.user) == ("drift", "site")
    assert load_harness_run(ctx, "other") is None and load_harness_run(ctx, "nope") is None
    assert load_harness_run(ctx, "../bad") is None


def test_the_rows_are_the_runs_own(backend: MemoryBackend) -> None:
    write_run(backend, "a", FROZEN, 0.5, minutes=0)
    write_run(backend, "b", FROZEN, 0.7, minutes=10)
    rows = load_harness_run_rows(stores(backend), "b")
    assert rows is not None and sorted(r.slice_kind for r in rows) == ["all", "frozen"]
    assert next(r for r in rows if r.slice_kind == "frozen").hit_rate == 0.7
    assert load_harness_run_rows(stores(backend), "nope") is None
