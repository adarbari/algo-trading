"""Run records for the Admin pages: nightly runs step by step, one run's detail with its
failures grouped by reason, its items; ``None`` for a run that is not there."""

from datetime import UTC, date, datetime

import pytest

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.read.context import StoreContext, open_stores
from algotrade.services.read.ops.runs import (
    failure_groups,
    load_nightly_runs,
    load_run,
    load_run_items,
)
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.runs import start_run
from algotrade_api.deps import ReadStore

NOW = datetime(2026, 10, 3, 2, tzinfo=UTC)


@pytest.fixture(scope="module")
def golden(api_golden: tuple[ReadStore, dict[str, str]]) -> StoreContext:
    store = api_golden[0]
    return open_stores(store.reader, store.configs, store.user)


def _stores(backend: MemoryBackend) -> StoreContext:
    return open_stores(StoreReader(backend), MemoryConfigStore({}), UserContext("local"))


def test_failure_groups_largest_first_with_examples_and_statuses() -> None:
    items = {f"T{i:02}": f"STALE_DATA: chain is for 2026-10-0{i % 2 + 1}" for i in range(12)}
    items |= {"A": "OK", "B": "NO_CHAIN", "C": "ERROR: timeout", "D": "SKIPPED: none due"}
    groups = failure_groups(items)
    assert [(g.reason, g.count) for g in groups] == [
        ("STALE_DATA: chain is for <date>", 12),
        ("ERROR: timeout", 1),
        ("NO_CHAIN", 1),
    ]
    assert groups[0].examples[:2] == ("T00", "T01") and len(groups[0].examples) == 10
    assert groups[0].statuses == (
        "STALE_DATA: chain is for 2026-10-01",
        "STALE_DATA: chain is for 2026-10-02",
    )


def test_nightly_runs_with_steps(golden: StoreContext) -> None:
    [run] = load_nightly_runs(golden, 5)
    assert (run.session, run.status, run.duration_s) == (date(2022, 11, 23), "partial", 300.0)
    steps = {s.name: s for s in run.steps}
    assert steps["bars"].counts == {"rows": 11}
    assert steps["chains"].status == "PARTIAL"
    assert run.problems == ("steps not complete: chains",)


def test_a_nightly_run_that_failed_early_shows_its_items_as_steps() -> None:
    backend = MemoryBackend()
    run = start_run("nightly", date(2026, 10, 2), NOW)
    run.items = {"universe-build": "FAILED"}
    run.stats = {"failed": ["no step succeeded"]}
    backend.runs.save(run)  # RUNNING: no finish time, no duration
    stores = _stores(backend)
    [summary] = load_nightly_runs(stores, limit=0)
    assert [(s.name, s.status) for s in summary.steps] == [("universe-build", "FAILED")]
    assert (summary.duration_s, summary.problems) == (None, ("no step succeeded",))
    detail = load_run(stores, run.run_id)
    assert detail is not None and detail.duration_s is None


def test_run_detail_groups_failures_by_reason(
    golden: StoreContext, api_golden: tuple[ReadStore, dict[str, str]]
) -> None:
    detail = load_run(golden, api_golden[1]["chains"])
    assert detail is not None and detail.items_total == 3
    assert detail.items_by_status == {"OK": 1, "NO_CHAIN": 1, "STALE_DATA": 1}
    groups = {g.reason: g for g in detail.failures}
    assert set(groups) == {"NO_CHAIN", "STALE_DATA: chain is for <date>"}
    assert groups["STALE_DATA: chain is for <date>"].examples == ("CCC",)


def test_run_items_every_item_with_its_code(
    golden: StoreContext, api_golden: tuple[ReadStore, dict[str, str]]
) -> None:
    items = load_run_items(golden, api_golden[1]["chains"])
    assert items is not None
    assert [(i.key, i.code, i.status) for i in items] == [
        ("AAA", "OK", "OK"),
        ("BBB", "NO_CHAIN", "NO_CHAIN"),
        ("CCC", "STALE_DATA", "STALE_DATA: chain is for 2022-11-21"),
    ]


def test_no_such_run_is_none(golden: StoreContext) -> None:
    for run_id in ("nope", ".hidden"):
        assert load_run(golden, run_id) is None
        assert load_run_items(golden, run_id) is None
